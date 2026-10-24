"""Offline protocol fixtures for the nine-task policy.

Real cases are the four recorded public samples in
``inbox/1024-test/自主实验赛道选手公开包/examples/sdk-fixtures.json`` and are passed
through ``lab_sdk.adapters.Adapter`` from the public package root, so the driver
sees exactly the canonical v2 instruction/observation the official SDK produces.

Everything else is a *protocol-synthetic* case: the raw instruction of the real
public sample for the same wave + robot is copied and only ``task_id`` (and, for
wave 1, the public per-task budget from ``contracts/rules-v1.json``) is replaced.
Synthetic cases are marked ``synthetic=True`` everywhere (JSON + Markdown) and
must never be reported as real recorded data.

This module never imports or executes the policy under test.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
NINE_TASK_DIR = TESTS_DIR.parent
DELIVERABLES_DIR = NINE_TASK_DIR.parent
REPO_ROOT = DELIVERABLES_DIR.parent

DEFAULT_PACKAGE_ROOT = REPO_ROOT / "inbox" / "1024-test" / "自主实验赛道选手公开包"
DEFAULT_POLICY_DIR = NINE_TASK_DIR / "src" / "my-policy"
DEFAULT_POLICY_SOURCE = "policy.py"

FIXTURES_REL = Path("examples") / "sdk-fixtures.json"
RULES_REL = Path("contracts") / "rules-v1.json"

ROBOTS = ("franka", "piper-dual")
WAVES = ("wave1", "wave2")

# Joint counts come from contracts/rules-v1.json strategy.arm_joint_count; keep
# them here only for inexpensive cross-checks.
ARM_JOINT_COUNT = {"franka": 7, "piper-dual": 6}
CANONICAL_SINGLE_ARM = {"arm"}
CANONICAL_DUAL_ARM = {"left", "right"}


def resolve_package_root(package_root=None):
    """Return the absolute public-package root, validating required files."""
    root = Path(package_root) if package_root else DEFAULT_PACKAGE_ROOT
    root = root.resolve()
    missing = [str(root / rel) for rel in (FIXTURES_REL, RULES_REL) if not (root / rel).is_file()]
    if missing:
        raise FileNotFoundError(
            "public package root is missing required files: " + ", ".join(missing)
        )
    return root


def ensure_sdk_importable(package_root):
    """Put the public package root on sys.path and import the official adapter."""
    root = str(Path(package_root).resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    from lab_sdk.adapters import Adapter, ContractError  # noqa: F401  (import side effect)

    return Adapter, ContractError


def load_rules(package_root):
    return json.loads((Path(package_root) / RULES_REL).read_text(encoding="utf-8"))


def rules_task_map(rules):
    return {task["task_id"]: task for task in rules["tasks"]}


def load_raw_fixtures(package_root):
    return json.loads((Path(package_root) / FIXTURES_REL).read_text(encoding="utf-8"))


@dataclass
class FixtureCase:
    """One canonical protocol case (real recorded sample or synthetic derivation)."""

    case_id: str
    wave: str
    robot: str
    task_id: str
    raw_instruction: dict
    raw_observation: dict
    provenance: dict
    synthetic: bool = False
    derived_from: str | None = None
    notes: list = field(default_factory=list)
    _adapter_cls: object = field(default=None, repr=False)

    # -- canonical SDK projection -------------------------------------------------
    def make_adapter(self):
        if self._adapter_cls is None:
            raise RuntimeError("adapter class is not bound to this fixture case")
        return self._adapter_cls(self.raw_instruction, wave=self.wave, robot=self.robot)

    def canonical_instruction(self):
        return self.make_adapter().instruction()

    def canonical_observation(self):
        return self.make_adapter().observation(self.raw_observation)

    # -- reporting ----------------------------------------------------------------
    def describe(self):
        return {
            "case_id": self.case_id,
            "wave": self.wave,
            "robot": self.robot,
            "task_id": self.task_id,
            "synthetic": self.synthetic,
            "derived_from": self.derived_from,
            "provenance": copy.deepcopy(self.provenance),
            "notes": list(self.notes),
        }


def _real_case(case_index, raw_case, adapter_cls):
    instruction = raw_case["instruction"]
    observation = raw_case["observation"]
    wave = raw_case["wave"]
    robot = raw_case["robot"]
    task_id = instruction["task_id"]
    provenance = copy.deepcopy(raw_case.get("provenance", {}))
    case_id = f"real:{wave}:{robot}:{task_id}"
    return FixtureCase(
        case_id=case_id,
        wave=wave,
        robot=robot,
        task_id=task_id,
        raw_instruction=copy.deepcopy(instruction),
        raw_observation=copy.deepcopy(observation),
        provenance=provenance,
        synthetic=False,
        derived_from=None,
        notes=[f"real recorded public sample #{case_index} from examples/sdk-fixtures.json"],
        _adapter_cls=adapter_cls,
    )


def _budget_from_rules(task_rule, wave):
    """Build the wave-1 public ``budget`` record from the frozen public rules."""
    budget = task_rule["budget"]
    if wave == "wave1":
        hz = budget["physics_hz"]
        sim_s = budget["simulation_seconds"]
        max_steps = int(round(sim_s * hz))
        max_calls = budget["max_api_calls"]
        return {
            "physics_steps": 0,
            "remaining_physics_steps": max_steps,
            "calls": 0,
            "remaining_calls": max_calls,
            "max_physics_steps": max_steps,
            "max_calls": max_calls,
            "physics_dt_s": 1.0 / hz,
            "inference_physics": "paused",
            "finished": False,
        }
    return None


def _synthetic_case(wave, robot, task_id, base_real, task_rule, adapter_cls):
    """Derive a protocol-synthetic case from the real sample of the same wave/robot."""
    instruction = copy.deepcopy(base_real.raw_instruction)
    instruction["task_id"] = task_id
    if wave == "wave1":
        # Same wave/robot shape; only the public per-task budget differs.
        instruction["budget"] = _budget_from_rules(task_rule, wave)
    # A derived observation keeps the same wave/robot proprioception shape. The
    # task-specific instrument/feedback fields are whatever the source sample
    # exposed; the driver re-derives time/proprioception/budget every step.
    observation = copy.deepcopy(base_real.raw_observation)
    provenance = {
        "synthetic": True,
        "derivation": "protocol-synthetic: real sample for the same wave/robot copied,"
                      " task_id replaced; no recorded trajectory or judge truth exists",
        "derived_from_case": base_real.case_id,
        "derived_from_instruction_sha256_original": base_real.provenance.get(
            "instruction_sha256_original"
        ),
    }
    notes = [
        "synthetic=True: protocol-shape derivation, NOT real recorded data",
        f"derived from {base_real.case_id}",
    ]
    if wave == "wave1":
        notes.append("wave1 budget replaced from contracts/rules-v1.json frozen public budget")
    return FixtureCase(
        case_id=f"synthetic:{wave}:{robot}:{task_id}",
        wave=wave,
        robot=robot,
        task_id=task_id,
        raw_instruction=instruction,
        raw_observation=observation,
        provenance=provenance,
        synthetic=True,
        derived_from=base_real.case_id,
        notes=notes,
        _adapter_cls=adapter_cls,
    )


def load_all_cases(package_root=None):
    """Return (real_cases, synthetic_cases) built from the public package."""
    root = resolve_package_root(package_root)
    adapter_cls, _ = ensure_sdk_importable(root)
    rules = load_rules(root)
    raw = load_raw_fixtures(package_root=root)
    if raw.get("schema") != "lab-sdk-public-fixtures/v1":
        raise ValueError(f"unexpected fixtures schema: {raw.get('schema')!r}")
    raw_cases = raw["cases"]
    real_cases = [_real_case(i, case, adapter_cls) for i, case in enumerate(raw_cases)]

    # Validate that the four real samples are the ones the task expects.
    real_by_key = {(c.wave, c.robot): c for c in real_cases}
    expected_real = {
        ("wave1", "franka"): "bottle_transfer",
        ("wave1", "piper-dual"): "bottle_transfer",
        ("wave2", "franka"): "C02",
        ("wave2", "piper-dual"): "C07",
    }
    for key, task_id in expected_real.items():
        if key not in real_by_key:
            raise ValueError(f"missing real public fixture for {key}")
        if real_by_key[key].task_id != task_id:
            raise ValueError(
                f"real fixture task mismatch for {key}: {real_by_key[key].task_id!r} != {task_id!r}"
            )

    task_rules = rules_task_map(rules)
    synthetic_cases = []
    for wave in WAVES:
        wave_tasks = [t["task_id"] for t in rules["tasks"] if t["wave"] == wave]
        for robot in ROBOTS:
            base_real = real_by_key[(wave, robot)]
            for task_id in wave_tasks:
                if task_id == base_real.task_id:
                    continue
                synthetic_cases.append(
                    _synthetic_case(
                        wave, robot, task_id, base_real, task_rules[task_id], adapter_cls
                    )
                )
    return real_cases, synthetic_cases


def find_case(cases, *, wave=None, robot=None, task_id=None, synthetic=None):
    matches = [
        c
        for c in cases
        if (wave is None or c.wave == wave)
        and (robot is None or c.robot == robot)
        and (task_id is None or c.task_id == task_id)
        and (synthetic is None or c.synthetic == synthetic)
    ]
    if len(matches) != 1:
        raise LookupError(f"expected exactly one fixture, found {len(matches)}")
    return matches[0]


def expected_finish_extra_steps(rules, task_id):
    return int(rules_task_map(rules)[task_id]["budget"]["finish_extra_physics_steps"])


def rules_for_case(rules, case):
    """Return the frozen public rules entry for a case's task."""
    return rules_task_map(rules)[case.task_id]


def case_budget_limits(rules, case):
    """Return (max_physics_steps, max_api_calls, finish_extra_steps, physics_hz, dt)."""
    task_rule = rules_for_case(rules, case)
    budget = task_rule["budget"]
    hz = float(budget["physics_hz"])
    dt = 1.0 / hz
    if case.wave == "wave1":
        max_steps = int(round(budget["simulation_seconds"] * hz))
    else:
        max_steps = int(budget["max_physics_steps"])
    return {
        "max_physics_steps": max_steps,
        "max_api_calls": int(budget["max_api_calls"]),
        "finish_extra_steps": int(budget["finish_extra_physics_steps"]),
        "physics_hz": hz,
        "dt": dt,
        "policy_cpu_seconds": int(budget.get("policy_cpu_seconds", 120)),
        "policy_wall_seconds": int(budget.get("policy_wall_seconds", 600)),
    }


def fixture_summary(real_cases, synthetic_cases):
    return {
        "real_count": len(real_cases),
        "synthetic_count": len(synthetic_cases),
        "real": [c.describe() for c in real_cases],
        "synthetic": [c.describe() for c in synthetic_cases],
        "notice": "Only 'real' cases are recorded public samples; 'synthetic' cases are"
                  " protocol-shape derivations and are never reported as real data.",
    }
