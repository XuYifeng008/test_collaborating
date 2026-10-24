"""Test suite for the offline nine-task protocol harness.

Real cases: the four recorded public SDK fixtures, driven through the official
``lab_sdk.adapters.Adapter``.  They carry no RGB payloads, so the policy is
expected to take its "perception unavailable -> safe abort" path; the tests only
assert protocol legality, budget compliance, the wave-appropriate finish
contract, determinism and safe-abort semantics, never task success.

C07 state-machine cases inject a **synthetic perception stub** into the policy's
module-level ``perceive`` hook and a **scripted balance stub**; they validate the
place -> stable reads -> single tare -> pour/read -> settle -> finish protocol
only.  They are never reported as physical task success.

All protocol-synthetic cases are derived from a real sample of the same wave and
robot (task_id replaced) and are flagged ``synthetic=True`` in every report.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import assertions
from assertions import Check
import episode as episode_mod
from episode import make_file_policy_factory, run_episode
import fixtures
from perception_stub import build_perception_patch

C07_GRIPPER_MOCK = {"stall_width_m": 0.052, "release_threshold_m": 0.055}
WAVE2_REQUIRED_HOLD_SECONDS = 1.2  # contract from the lead's aligned assertion set


# ----------------------------------------------------------------------------------
# result model
# ----------------------------------------------------------------------------------
@dataclass
class TestResult:
    test_id: str
    title: str
    category: str
    status: str = "PASS"
    checks: list = field(default_factory=list)
    episodes: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    error: str | None = None
    duration_s: float = 0.0

    def add_checks(self, checks):
        self.checks.extend(checks)

    def add_episode(self, result, label):
        self.episodes.append({"label": label, "result": result.to_dict(include_action_log=False)})

    def add_note(self, note):
        self.notes.append(note)

    def finalize(self):
        if self.status == "SKIP":
            return
        if self.error:
            self.status = "ERROR"
            return
        failed = [c for c in self.checks if not c.ok and c.severity == "fail"]
        self.status = "FAIL" if failed else "PASS"

    def to_dict(self):
        summary = assertions.aggregate_checks(self.checks)
        return {
            "test_id": self.test_id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "check_summary": summary,
            "checks": [check.to_dict() for check in self.checks],
            "episodes": self.episodes,
            "notes": self.notes,
            "data": self.data,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
        }


@dataclass
class RunOptions:
    suite: str = "full"  # "full" | "self_check"
    include_synthetic: bool = True
    include_c07_injected: bool = True
    real_determinism_runs: int = 2
    synthetic_max_iterations: int = 260
    synthetic_wall_limit_s: float = 60.0
    c07_wall_limit_s: float = 240.0
    real_wall_limit_s: float = 120.0


@dataclass
class SuiteContext:
    package_root: Path
    policy_dir: Path
    policy_source: str
    rules: dict
    real_cases: list
    synthetic_cases: list
    policy_present: bool
    policy_meta: dict = field(default_factory=dict)

    @property
    def all_cases(self):
        return list(self.real_cases) + list(self.synthetic_cases)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _policy_meta(policy_dir, policy_source):
    policy_dir = Path(policy_dir)
    entry = policy_dir / policy_source
    files = {}
    if policy_dir.is_dir():
        for path in sorted(policy_dir.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            files[str(path.relative_to(policy_dir))] = {
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "role": "entrypoint" if path == entry else "policy_file",
            }
    return {
        "policy_dir": str(policy_dir),
        "policy_source": policy_source,
        "entrypoint_exists": entry.is_file(),
        "files": files,
    }


def build_context(package_root=None, policy_dir=None, policy_source="policy.py"):
    root = fixtures.resolve_package_root(package_root)
    policy_dir = Path(policy_dir) if policy_dir else fixtures.DEFAULT_POLICY_DIR
    real_cases, synthetic_cases = fixtures.load_all_cases(root)
    rules = fixtures.load_rules(root)
    present = (policy_dir / policy_source).is_file()
    return SuiteContext(
        package_root=root,
        policy_dir=policy_dir,
        policy_source=policy_source,
        rules=rules,
        real_cases=real_cases,
        synthetic_cases=synthetic_cases,
        policy_present=present,
        policy_meta=_policy_meta(policy_dir, policy_source),
    )


def _policy_factory(ctx):
    return make_file_policy_factory(ctx.policy_dir, ctx.policy_source)


# ----------------------------------------------------------------------------------
# static fixture / adapter tests
# ----------------------------------------------------------------------------------
def test_fixture_integrity(ctx, options, result):
    result.add_note("real vs synthetic is distinguished in fixtures + report; synthetic never presented as real")
    result.add_checks(
        [
            Check("four_real_public_samples", len(ctx.real_cases) == 4,
                  f"count={len(ctx.real_cases)}"),
            Check("real_wave_robot_task_matrix",
                  {(c.wave, c.robot, c.task_id) for c in ctx.real_cases}
                  == {
                      ("wave1", "franka", "bottle_transfer"),
                      ("wave1", "piper-dual", "bottle_transfer"),
                      ("wave2", "franka", "C02"),
                      ("wave2", "piper-dual", "C07"),
                  },
                  f"matrix={sorted((c.wave, c.robot, c.task_id) for c in ctx.real_cases)}"),
            Check("expected_synthetic_count",
                  {c.task_id for c in ctx.synthetic_cases}
                  == {"beaker_place", "balance_load", "stirrer_knob", "tube_insert",
                      "C01", "C02", "C04", "C07"},
                  f"tasks={sorted({c.task_id for c in ctx.synthetic_cases})} count={len(ctx.synthetic_cases)}"),
        ]
    )
    for case in ctx.real_cases:
        provenance = case.provenance or {}
        checks = [
            Check(f"real[{case.case_id}].not_synthetic", case.synthetic is False, "synthetic=False"),
            Check(f"real[{case.case_id}].release", bool(provenance.get("source_release")),
                  f"source_release={provenance.get('source_release')!r}"),
            Check(f"real[{case.case_id}].instruction_sha",
                  isinstance(provenance.get("instruction_sha256_original"), str),
                  f"sha={provenance.get('instruction_sha256_original')!r}"),
            Check(f"real[{case.case_id}].observation_sha",
                  isinstance(provenance.get("observation_sha256_original"), str),
                  f"sha={provenance.get('observation_sha256_original')!r}"),
        ]
        result.add_checks(checks)
        result.data.setdefault("real_cases", []).append(
            {
                "case_id": case.case_id,
                "wave": case.wave,
                "robot": case.robot,
                "task_id": case.task_id,
                "provenance": case.provenance,
            }
        )
    for case in ctx.synthetic_cases:
        result.add_checks(
            [
                Check(f"synthetic[{case.case_id}].flagged", case.synthetic is True, "synthetic=True"),
                Check(f"synthetic[{case.case_id}].derived_from", bool(case.derived_from),
                      f"derived_from={case.derived_from!r}"),
                Check(f"synthetic[{case.case_id}].no_recorded_claim",
                      case.provenance.get("synthetic") is True,
                      "provenance marks protocol-synthetic derivation"),
            ]
        )
    result.data["synthetic_cases"] = [case.describe() for case in ctx.synthetic_cases]
    result.data["notice"] = fixtures.fixture_summary(ctx.real_cases, ctx.synthetic_cases)["notice"]


def test_adapter_canonical_projection(ctx, options, result):
    for case in ctx.all_cases:
        try:
            instruction = case.canonical_instruction()
            observation = case.canonical_observation()
        except Exception as exc:  # noqa: BLE001
            result.add_checks(
                [Check(f"{case.case_id}.adapter_projection", False, f"{type(exc).__name__}: {exc}")]
            )
            continue
        checks = [Check(f"{case.case_id}.adapter_projection", True, "Adapter built canonical v2 pair")]
        checks += assertions.check_canonical_instruction(case, instruction, ctx.rules)
        checks += assertions.check_canonical_observation(case, observation, instruction)
        checks += assertions.check_observation_gripper_ranges(case, instruction)
        result.add_checks(checks)
    result.data["cases_checked"] = len(ctx.all_cases)


def test_frequency_semantics(ctx, options, result):
    for case in ctx.all_cases:
        instruction = case.canonical_instruction()
        result.add_checks(assertions.check_frequency_semantics(case, instruction))
    result.data["expected"] = {
        "wave1": {"frequency_hz": 240, "step_seconds": 1.0 / 240.0, "finish_extra_physics_steps": 720},
        "wave2": {"frequency_hz": 120, "step_seconds": 1.0 / 120.0, "finish_extra_physics_steps": 0},
    }


def test_joint_order_mapping(ctx, options, result):
    for case in ctx.all_cases:
        result.add_checks(assertions.check_joint_order_mapping(case))
    result.data["expected_joint_counts"] = dict(fixtures.ARM_JOINT_COUNT)


def test_adapter_action_boundary(ctx, options, result):
    for case in ctx.real_cases:
        result.add_checks(assertions.check_adapter_action_boundary(case))
    # Synthetic C07 is the same wave/robot sample with the task id replaced; the
    # instrument matrix is covered by the real C07 sample above.
    result.data["notice"] = "official Adapter accept/reject matrix on the four real samples"


# ----------------------------------------------------------------------------------
# driver self-check (negative stubs prove the driver rejects illegal policies)
# ----------------------------------------------------------------------------------
class _StubPolicyBase:
    observation_images = False

    def __init__(self, kind):
        self.kind = kind
        self.instruction = None

    def reset(self, instruction):
        if self.kind == "reset_raises":
            raise RuntimeError("stub reset failure")
        self.instruction = instruction

    def _first_arm_positions(self, observation):
        proprio = observation.get("proprioception") or {}
        for name, item in proprio.items():
            positions = item.get("arm_joint_positions")
            if isinstance(positions, list) and positions:
                return name, list(positions)
        return None, None

    def act(self, observation):
        kind = self.kind
        if kind == "act_raises":
            raise RuntimeError("stub act failure")
        if kind == "no_finish":
            return {"arms": {}, "steps": 1}
        if kind == "overspend":
            return {"arms": {}, "steps": 120}
        if kind == "finish_inexact":
            return {"finish": 1}
        if kind == "bad_steps_zero":
            return {"arms": {}, "steps": 0}
        if kind == "mixed_instrument":
            return {
                "instrument": {"device": "competition_balance", "method": "read"},
                "arms": {},
                "steps": 1,
            }
        if kind == "instrument_only":
            return {"instrument": {"device": "competition_balance", "method": "read"}}
        arm, positions = self._first_arm_positions(observation)
        if kind == "bad_joint_count":
            return {"arms": {arm: {"positions": positions[:-1]}}, "steps": 1}
        if kind == "nonfinite":
            bad = list(positions)
            bad[0] = float("nan")
            return {"arms": {arm: {"positions": bad}}, "steps": 1}
        if kind == "unknown_field":
            return {"jump": True}
        return {"arms": {}, "steps": 1}


def _stub_factory(kind):
    return lambda: _StubPolicyBase(kind)


def test_driver_self_check(ctx, options, result):
    case = fixtures.find_case(ctx.real_cases, wave="wave1", robot="franka")
    c07_case = fixtures.find_case(ctx.real_cases, wave="wave2", robot="piper-dual", task_id="C07")

    def base_kwargs(**overrides):
        kwargs = {
            "package_root": ctx.package_root,
            "rules": ctx.rules,
            "mode": "full",
            "max_iterations": 1600,
            "wall_clock_limit_s": 60.0,
        }
        kwargs.update(overrides)
        return kwargs

    negative_expectations = {
        "no_finish": "budget_calls_exceeded",
        "overspend": "budget_steps_exceeded",
        "bad_joint_count": "invalid_action",
        "bad_steps_zero": "invalid_action",
        "finish_inexact": "invalid_action",
        "nonfinite": "invalid_action",
        "unknown_field": "invalid_action",
        "mixed_instrument": "invalid_action",
        "instrument_only": "invalid_action",
        "act_raises": "act_exception",
        "reset_raises": "reset_exception",
    }
    for kind, expected in negative_expectations.items():
        target_case = c07_case if kind in ("mixed_instrument",) else case
        stub_result = run_episode(target_case, **base_kwargs(policy_factory=_stub_factory(kind)))
        codes = stub_result.violation_codes()
        detail_ok = True
        if kind == "mixed_instrument":
            detail_ok = any(
                "mix" in violation.get("detail", "") for violation in stub_result.violations
            )
        result.add_checks(
            [
                Check(f"selfcheck.{kind}.rejected", expected in codes,
                      f"expected violation {expected!r}, got {codes}"),
                Check(f"selfcheck.{kind}.not_finished", not stub_result.finished,
                      f"cap_reason={stub_result.cap_reason!r}"),
                Check(f"selfcheck.{kind}.detail", detail_ok,
                      f"violations={stub_result.violations[:2]}"),
            ]
        )

    # Positive control: the public examples/minimal policy must run cleanly.
    minimal_dir = ctx.package_root / "examples" / "minimal"
    positive = run_episode(
        case,
        **base_kwargs(policy_factory=make_file_policy_factory(minimal_dir, "policy.py")),
    )
    result.add_checks(
        [
            Check("selfcheck.positive_minimal.finished", positive.finished,
                  f"cap_reason={positive.cap_reason!r}"),
            Check("selfcheck.positive_minimal.no_violations", not positive.violations,
                  f"violations={positive.violation_codes()}"),
            Check("selfcheck.positive_minimal.finish_accounting",
                  positive.stats.get("finish_extra_physics_steps") == 720,
                  f"finish steps={positive.stats.get('finish_extra_physics_steps')}"),
        ]
    )
    result.add_episode(positive, "positive_control_minimal_policy")
    result.data["notice"] = (
        "negative stubs prove the driver rejects illegal actions / budgets / exceptions;"
        " the positive control runs the public examples/minimal policy"
    )


# ----------------------------------------------------------------------------------
# policy submission / source tests
# ----------------------------------------------------------------------------------
def test_policy_submission_source(ctx, options, result):
    if not ctx.policy_present:
        result.status = "SKIP"
        result.add_note("policy entrypoint not found")
        return
    result.add_checks(assertions.check_policy_submission(ctx.policy_dir, ctx.policy_source))
    scan = assertions.scan_policy_frequency_hardcode(ctx.policy_dir, ctx.policy_source)
    result.add_checks(assertions.check_policy_frequency_source(scan))
    result.data["policy_meta"] = ctx.policy_meta
    result.data["frequency_scan"] = scan
    try:
        module = episode_mod.load_policy_module(ctx.policy_dir, ctx.policy_source, fresh=True)
        policy_cls = getattr(module, "Policy", None)
        result.add_checks(
            [
                Check("policy_module_imports", True, f"imported {ctx.policy_source}"),
                Check("policy_class_callable", callable(policy_cls), f"Policy={policy_cls!r}"),
                Check("policy_no_arg_constructor", callable(policy_cls),
                      "constructed in every episode below"),
                Check("policy_perceive_hook_present", callable(getattr(module, "perceive", None)),
                      "module-level perceive(observation, kind, camera=None) hook",
                      severity="warn"),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        result.add_checks([Check("policy_module_imports", False, f"{type(exc).__name__}: {exc}")])


# ----------------------------------------------------------------------------------
# real recorded-sample episodes (no images -> expected safe abort)
# ----------------------------------------------------------------------------------
def _run_real_case(ctx, options, case):
    factory = _policy_factory(ctx)
    kwargs = {
        "package_root": ctx.package_root,
        "rules": ctx.rules,
        "policy_factory": factory,
        "mode": "full",
        "wall_clock_limit_s": options.real_wall_limit_s,
        "keep_action_log": False,
    }
    first = run_episode(case, **kwargs)
    second = run_episode(case, **kwargs) if options.real_determinism_runs > 1 else None
    return first, second


def test_real_case(ctx, options, case):
    test_id = f"real:{case.wave}:{case.robot}:{case.task_id}"
    result = TestResult(
        test_id=test_id,
        title=f"real recorded sample {case.wave}/{case.robot}/{case.task_id}",
        category="real_fixture_episode",
    )
    first, second = _run_real_case(ctx, options, case)
    result.add_checks(
        assertions.evaluate_full_episode(
            case, first, ctx.rules, required_hold_seconds=WAVE2_REQUIRED_HOLD_SECONDS
        )
    )
    if second is not None:
        result.add_checks(assertions.check_determinism(first, second))
        result.add_episode(second, "run2")
    if case.wave == "wave2" and case.task_id == "C07":
        result.add_checks(assertions.check_c07_perception_unavailable(first))
    result.add_episode(first, "run1")
    result.add_note(
        "public fixture has no RGB payloads; expected policy path is"
        " 'perception unavailable -> safe retract + hold + finish'. This is a"
        " protocol/safe-abort result only - no task success is claimed."
    )
    result.add_note(
        f"outcome=safe_abort_no_perception (finished={first.finished}, "
        f"calls={first.stats.get('act_calls')}, physics_steps={first.stats.get('physics_steps_tracked')})"
    )
    result.data["outcome"] = "SAFE_ABORT_NO_PERCEPTION"
    return result


# ----------------------------------------------------------------------------------
# C07 injected-perception state-machine tests
# ----------------------------------------------------------------------------------
def _run_c07(ctx, options, *, balance_mode, gripper_mock=C07_GRIPPER_MOCK,
             determinism_runs=1, missing_perception=None):
    case = fixtures.find_case(ctx.real_cases, wave="wave2", robot="piper-dual", task_id="C07")
    stub, patch = build_perception_patch(missing=missing_perception)

    def factory():
        return make_file_policy_factory(
            ctx.policy_dir, ctx.policy_source, module_patch=patch
        )()

    kwargs = {
        "package_root": ctx.package_root,
        "rules": ctx.rules,
        "policy_factory": factory,
        "mode": "full",
        "wall_clock_limit_s": options.c07_wall_limit_s,
        "balance_mode": balance_mode,
        "gripper_mock": gripper_mock,
        "keep_action_log": True,
    }
    runs = [run_episode(case, **kwargs) for _ in range(max(1, determinism_runs))]
    return runs[0], runs[1] if len(runs) > 1 else None, stub


def _c07_test_header(result, stub, balance_mode):
    result.add_note(
        "SYNTHETIC perception stub injected into policy.perceive (no real camera);"
        " scripted balance receipts (FakeBalance) are not real measurements."
    )
    result.add_note(
        "validates state machine + protocol only: stable-gated single tare, no mixed"
        " instrument actions, net-mass reads, wave2 hold-before-finish, determinism."
    )
    result.data["perception_stub"] = stub.summary()
    result.data["balance_mode"] = balance_mode
    result.data["synthetic"] = True


def test_c07_nominal(ctx, options, result):
    first, second, stub = _run_c07(ctx, options, balance_mode="nominal", determinism_runs=2)
    case = fixtures.find_case(ctx.real_cases, wave="wave2", robot="piper-dual", task_id="C07")
    result.add_checks(
        assertions.evaluate_full_episode(
            case, first, ctx.rules, required_hold_seconds=WAVE2_REQUIRED_HOLD_SECONDS
        )
    )
    result.add_checks(assertions.check_c07_nominal(first))
    if second is not None:
        result.add_checks(assertions.check_determinism(first, second))
        result.add_episode(second, "run2")
    result.add_episode(first, "run1")
    _c07_test_header(result, stub, "nominal")


def test_c07_abnormal_unstable(ctx, options, result):
    first, _, stub = _run_c07(ctx, options, balance_mode="abnormal_unstable", determinism_runs=1)
    case = fixtures.find_case(ctx.real_cases, wave="wave2", robot="piper-dual", task_id="C07")
    result.add_checks(
        assertions.evaluate_full_episode(
            case, first, ctx.rules, required_hold_seconds=WAVE2_REQUIRED_HOLD_SECONDS
        )
    )
    result.add_checks(assertions.check_c07_abnormal(first, expect_recovery=True))
    result.add_episode(first, "run1")
    _c07_test_header(result, stub, "abnormal_unstable")


def test_c07_abnormal_missing(ctx, options, result):
    first, _, stub = _run_c07(ctx, options, balance_mode="abnormal_missing", determinism_runs=1)
    case = fixtures.find_case(ctx.real_cases, wave="wave2", robot="piper-dual", task_id="C07")
    result.add_checks(
        assertions.evaluate_full_episode(
            case, first, ctx.rules, required_hold_seconds=WAVE2_REQUIRED_HOLD_SECONDS
        )
    )
    result.add_checks(assertions.check_c07_abnormal(first, expect_recovery=True))
    result.add_episode(first, "run1")
    _c07_test_header(result, stub, "abnormal_missing")


def test_c07_persistent_abnormal(ctx, options, result):
    first, _, stub = _run_c07(ctx, options, balance_mode="abnormal_persistent", determinism_runs=1)
    case = fixtures.find_case(ctx.real_cases, wave="wave2", robot="piper-dual", task_id="C07")
    result.add_checks(
        assertions.evaluate_full_episode(
            case, first, ctx.rules, required_hold_seconds=WAVE2_REQUIRED_HOLD_SECONDS
        )
    )
    result.add_checks(assertions.check_c07_abnormal(first, expect_recovery=False))
    result.add_episode(first, "run1")
    _c07_test_header(result, stub, "abnormal_persistent")
    result.add_note(
        "persistent abnormal reads: policy is allowed to safe-abort, but must not"
        " claim a measured 10 g success (no second valid tare, no valid net-mass read)."
    )


# ----------------------------------------------------------------------------------
# protocol-synthetic smoke tests (all nine tasks x both robots x both waves)
# ----------------------------------------------------------------------------------
def _synthetic_group(ctx, options, result, wave):
    factory = _policy_factory(ctx)
    cases = [case for case in ctx.synthetic_cases if case.wave == wave]
    for case in cases:
        kwargs = {
            "package_root": ctx.package_root,
            "rules": ctx.rules,
            "policy_factory": factory,
            "mode": "smoke",
            "max_iterations": options.synthetic_max_iterations,
            "wall_clock_limit_s": options.synthetic_wall_limit_s,
            "keep_action_log": False,
        }
        run = run_episode(case, **kwargs)
        codes = run.violation_codes()
        result.add_checks(
            [
                Check(f"{case.case_id}.no_exception", run.exception is None,
                      f"exception={run.exception}"),
                Check(f"{case.case_id}.legal_actions", "invalid_action" not in codes,
                      f"violations={codes}"),
                Check(f"{case.case_id}.no_budget_overflow",
                      not any(code.startswith("budget_") for code in codes),
                      f"budget={run.budget}"),
                Check(f"{case.case_id}.ran_act_loop", run.stats.get("act_calls", 0) >= 1,
                      f"act_calls={run.stats.get('act_calls')}"),
            ]
        )
        result.data.setdefault("cases", []).append(
            {
                "case_id": case.case_id,
                "wave": case.wave,
                "robot": case.robot,
                "task_id": case.task_id,
                "synthetic": True,
                "finished": run.finished,
                "cap_reason": run.cap_reason,
                "violation_codes": codes,
                "stats": {
                    "act_calls": run.stats.get("act_calls"),
                    "physics_steps": run.stats.get("physics_steps_tracked"),
                    "terminal_hold_steps": run.stats.get("terminal_hold_steps"),
                },
            }
        )
        result.add_episode(run, "smoke")
    result.data["notice"] = (
        "synthetic protocol-shape cases (task_id derived from the real sample of the"
        " same wave/robot); no images -> safe abort path, no task success claimed"
    )


def test_synthetic_wave1(ctx, options, result):
    _synthetic_group(ctx, options, result, "wave1")


def test_synthetic_wave2(ctx, options, result):
    _synthetic_group(ctx, options, result, "wave2")


# ----------------------------------------------------------------------------------
# suite orchestration
# ----------------------------------------------------------------------------------
def _run_one(fn, ctx, options, *args, result=None):
    created = result is None
    if created:
        result = TestResult(test_id="", title="", category="")
    started = time.perf_counter()
    try:
        if created:
            outcome = fn(ctx, options, *args)
            if not isinstance(outcome, TestResult):
                raise TypeError(f"{getattr(fn, '__name__', fn)} did not return a TestResult")
            result = outcome
        else:
            fn(ctx, options, result, *args)
    except Exception:  # noqa: BLE001 - a crashing test is an ERROR, never a silent pass
        result.error = traceback.format_exc(limit=8)
    result.duration_s = time.perf_counter() - started
    result.finalize()
    if not result.test_id:
        result.test_id = getattr(fn, "__name__", "unnamed")
    if not result.title:
        result.title = result.test_id
    if not result.category:
        result.category = "misc"
    return result


def run_all(ctx, options=None):
    options = options or RunOptions()
    results = []
    results.append(_run_one(test_fixture_integrity, ctx, options,
                            result=TestResult("fixtures:integrity", "public fixture identity + synthetic labelling",
                                              "fixtures")))
    results.append(_run_one(test_adapter_canonical_projection, ctx, options,
                            result=TestResult("adapter:canonical_projection",
                                              "Adapter canonical v2 instruction/observation",
                                              "fixtures")))
    results.append(_run_one(test_frequency_semantics, ctx, options,
                            result=TestResult("protocol:frequency_semantics",
                                              "two-wave clock + native finish semantics",
                                              "protocol")))
    results.append(_run_one(test_joint_order_mapping, ctx, options,
                            result=TestResult("protocol:joint_order_mapping",
                                              "joint counts/order and dual-PiPER arm mapping",
                                              "protocol")))
    results.append(_run_one(test_adapter_action_boundary, ctx, options,
                            result=TestResult("adapter:action_boundary",
                                              "official Adapter accept/reject matrix",
                                              "protocol")))
    results.append(_run_one(test_driver_self_check, ctx, options,
                            result=TestResult("driver:self_check",
                                              "negative stubs rejected + positive minimal control",
                                              "driver")))

    policy_tests = []
    if ctx.policy_present and options.suite != "self_check":
        policy_tests.append(_run_one(test_policy_submission_source, ctx, options,
                                     result=TestResult("policy:submission_source",
                                                       "submission.json / entrypoint / frequency source scan",
                                                       "policy")))
        for case in ctx.real_cases:
            policy_tests.append(_run_one(test_real_case, ctx, options, case))
        if options.include_c07_injected:
            policy_tests.append(_run_one(test_c07_nominal, ctx, options,
                                         result=TestResult("c07:nominal_tare_state_machine",
                                                           "C07 place->stable reads->single tare->pour->read->settle->finish",
                                                           "c07_state_machine")))
            policy_tests.append(_run_one(test_c07_abnormal_unstable, ctx, options,
                                         result=TestResult("c07:abnormal_unstable_receipt",
                                                           "C07 unstable receipt is not treated as valid mass",
                                                           "c07_state_machine")))
            policy_tests.append(_run_one(test_c07_abnormal_missing, ctx, options,
                                         result=TestResult("c07:abnormal_missing_receipt",
                                                           "C07 missing-field receipt is not treated as valid mass",
                                                           "c07_state_machine")))
            policy_tests.append(_run_one(test_c07_persistent_abnormal, ctx, options,
                                         result=TestResult("c07:persistent_abnormal_safe_abort",
                                                           "C07 persistent abnormal reads -> safe abort, no success claim",
                                                           "c07_state_machine")))
        if options.include_synthetic:
            policy_tests.append(_run_one(test_synthetic_wave1, ctx, options,
                                         result=TestResult("synthetic:wave1_smoke",
                                                           "wave1 protocol-synthetic cases smoke",
                                                           "synthetic_smoke")))
            policy_tests.append(_run_one(test_synthetic_wave2, ctx, options,
                                         result=TestResult("synthetic:wave2_smoke",
                                                           "wave2 protocol-synthetic cases smoke",
                                                           "synthetic_smoke")))
    elif not ctx.policy_present:
        skipped = TestResult("policy:regression_suite", "policy regression suite", "policy")
        skipped.status = "SKIP"
        skipped.add_note(
            f"policy entrypoint not found at {ctx.policy_dir / ctx.policy_source};"
            " fixture/Adapter/driver self-check only"
        )
        policy_tests.append(skipped)
    else:
        skipped = TestResult("policy:regression_suite", "policy regression suite", "policy")
        skipped.status = "SKIP"
        skipped.add_note("--self-check requested: policy regression tests skipped")
        policy_tests.append(skipped)
    results.extend(policy_tests)

    statuses = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for entry in results:
        statuses[entry.status] = statuses.get(entry.status, 0) + 1
    if not ctx.policy_present:
        suite_status = "policy_missing"
    elif options.suite == "self_check":
        suite_status = "self_check_only"
    elif statuses["FAIL"] or statuses["ERROR"]:
        suite_status = "fail"
    else:
        suite_status = "pass"
    return {
        "suite_status": suite_status,
        "results": results,
        "statuses": statuses,
        "context": ctx,
        "options": options,
    }
