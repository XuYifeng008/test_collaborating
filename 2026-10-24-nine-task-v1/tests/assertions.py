"""Reusable checks for the offline nine-task protocol harness.

Every helper returns a list of :class:`Check` records. ``severity='fail'`` checks
decide a test's PASS/FAIL status; ``severity='warn'`` checks are reported only.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from fixtures import ARM_JOINT_COUNT, case_budget_limits, rules_for_case


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "fail"

    def to_dict(self):
        return {
            "name": self.name,
            "ok": bool(self.ok),
            "detail": self.detail,
            "severity": self.severity,
        }


def approx(a, b, tol=1e-12):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _fmt(value):
    if isinstance(value, float):
        return f"{value:.12g}"
    return repr(value)


def check_canonical_instruction(case, instruction, rules):
    """Public contract checks on the canonical v2 instruction for one case."""
    checks = []
    task_rule = rules_for_case(rules, case)
    budget = case_budget_limits(rules, case)
    hz = budget["physics_hz"]
    dt = budget["dt"]

    def add(name, ok, detail=""):
        checks.append(Check(name, ok, detail))

    add("canonical_schema", instruction.get("schema") == "lab-instruction/v2",
        f"schema={instruction.get('schema')!r}")
    add("backend_wave", instruction.get("backend_wave") == case.wave,
        f"backend_wave={instruction.get('backend_wave')!r}")
    add("robot_profile", instruction.get("robot_profile") == case.robot,
        f"robot_profile={instruction.get('robot_profile')!r}")
    add("task_id_preserved", instruction.get("task_id") == case.task_id,
        f"task_id={instruction.get('task_id')!r}")

    physics = instruction.get("physics") or {}
    add("physics_step_seconds", approx(physics.get("step_seconds"), dt, 1e-12),
        f"step_seconds={physics.get('step_seconds')!r} expected={dt!r}")
    add("physics_frequency_hz", approx(physics.get("frequency_hz"), hz, 1e-9),
        f"frequency_hz={physics.get('frequency_hz')!r} expected={hz!r}")
    add("maximum_steps_per_action",
        physics.get("maximum_steps_per_action") == 120,
        f"value={physics.get('maximum_steps_per_action')!r}")

    finish = instruction.get("finish") or {}
    add("finish_extra_physics_steps",
        finish.get("extra_physics_steps") == budget["finish_extra_steps"],
        f"value={finish.get('extra_physics_steps')!r} expected={budget['finish_extra_steps']}")
    add("finish_behavior_mentions_native", isinstance(finish.get("behavior"), str),
        f"behavior={finish.get('behavior')!r}")

    strategy = rules["strategy"]
    gripper_ranges = strategy["gripper_range_m_by_wave_robot"][case.wave]
    expected_arms = set(strategy["canonical_arms"][case.robot])
    arms = instruction.get("arms") or {}
    add("arms_canonical_set", set(arms) == expected_arms,
        f"arms={sorted(arms)} expected={sorted(expected_arms)}")
    joint_count = ARM_JOINT_COUNT[case.robot]
    for arm_name, spec in arms.items():
        add(f"arm[{arm_name}].joint_position_count",
            spec.get("joint_position_count") == joint_count,
            f"value={spec.get('joint_position_count')!r} expected={joint_count}")
        names = spec.get("joint_names")
        add(f"arm[{arm_name}].joint_names_len",
            isinstance(names, list) and len(names) == joint_count,
            f"len={len(names) if isinstance(names, list) else names!r}")
        add(f"arm[{arm_name}].position_unit", spec.get("position_unit") == "rad",
            f"unit={spec.get('position_unit')!r}")
        expected_range = [0.0, float(gripper_ranges[case.robot][1])]
        add(f"arm[{arm_name}].gripper_range",
            isinstance(spec.get("gripper_width_m"), list)
            and len(spec["gripper_width_m"]) == 2
            and approx(spec["gripper_width_m"][0], expected_range[0], 1e-12)
            and approx(spec["gripper_width_m"][1], expected_range[1], 1e-12),
            f"range={spec.get('gripper_width_m')!r} expected={expected_range!r}")

    actions = instruction.get("actions") or {}
    action_arms = actions.get("arms") or {}
    add("actions_arms_match_instruction_arms", set(action_arms) == set(arms),
        f"actions.arms={sorted(action_arms)} arms={sorted(arms)}")
    add("actions_maximum_steps", actions.get("maximum_steps") == 120,
        f"value={actions.get('maximum_steps')!r}")

    kinematics = instruction.get("robot_kinematics") or {}
    add("kinematics_arm_set", set(kinematics) == set(arms),
        f"kinematics={sorted(kinematics)} arms={sorted(arms)}")
    for arm_name, kin in kinematics.items():
        arm_names = kin.get("arm_names")
        add(f"kinematics[{arm_name}].arm_names_count",
            isinstance(arm_names, list) and len(arm_names) == joint_count,
            f"len={len(arm_names) if isinstance(arm_names, list) else arm_names!r}")
    for arm_name in arms:
        spec_names = arms[arm_name].get("joint_names")
        kin_names = (kinematics.get(arm_name) or {}).get("arm_names")
        add(f"arm[{arm_name}].joint_order_matches_kinematics",
            isinstance(spec_names, list) and spec_names == kin_names,
            f"arm order={spec_names!r} kinematics order={kin_names!r}")

    if case.wave == "wave1":
        raw_budget = instruction.get("budget") or {}
        add("wave1_budget_present", bool(raw_budget), f"budget keys={sorted(raw_budget)}")
        expected_steps = int(round(task_rule["budget"]["simulation_seconds"] * hz))
        add("wave1_budget_max_physics_steps",
            raw_budget.get("max_physics_steps") == expected_steps,
            f"value={raw_budget.get('max_physics_steps')!r} expected={expected_steps}")
        add("wave1_budget_max_calls",
            raw_budget.get("max_calls") == task_rule["budget"]["max_api_calls"],
            f"value={raw_budget.get('max_calls')!r}")
        add("wave1_budget_physics_dt",
            approx(raw_budget.get("physics_dt_s"), dt, 1e-12),
            f"value={raw_budget.get('physics_dt_s')!r}")
    else:
        add("wave2_no_public_step_budget", "budget" not in instruction,
            "wave2 instructions expose no remaining-step budget (driver self-accumulates)")
    return checks


def check_canonical_observation(case, observation, instruction):
    checks = []

    def add(name, ok, detail=""):
        checks.append(Check(name, ok, detail))

    arms = instruction.get("arms") or {}
    add("canonical_schema", observation.get("schema") == "lab-observation/v2",
        f"schema={observation.get('schema')!r}")
    add("backend_wave", observation.get("backend_wave") == case.wave,
        f"backend_wave={observation.get('backend_wave')!r}")
    add("robot_profile", observation.get("robot_profile") == case.robot,
        f"robot_profile={observation.get('robot_profile')!r}")
    add("simulation_time_finite",
        isinstance(observation.get("simulation_time_s"), (int, float))
        and math.isfinite(float(observation["simulation_time_s"])),
        f"simulation_time_s={observation.get('simulation_time_s')!r}")
    add("observation_not_finished", observation.get("finished") is False,
        f"finished={observation.get('finished')!r}")
    proprio = observation.get("proprioception") or {}
    add("proprioception_arm_set", set(proprio) == set(arms),
        f"proprio={sorted(proprio)} arms={sorted(arms)}")
    for arm_name, spec in arms.items():
        item = proprio.get(arm_name) or {}
        names = item.get("arm_joint_names")
        expected = spec.get("joint_names")
        add(f"proprio[{arm_name}].joint_names",
            isinstance(names, list) and names == expected,
            f"names={names!r} expected={expected!r}")
        positions = item.get("arm_joint_positions")
        add(f"proprio[{arm_name}].joint_positions_len",
            isinstance(positions, list) and len(positions) == ARM_JOINT_COUNT[case.robot],
            f"len={len(positions) if isinstance(positions, list) else positions!r}")
        add(f"proprio[{arm_name}].all_finite",
            isinstance(positions, list) and all(isinstance(v, (int, float)) and math.isfinite(v) for v in positions),
            "joint positions must be finite")
    if case.wave == "wave1":
        add("wave1_observation_budget", isinstance(observation.get("budget"), dict),
            f"budget keys={sorted(observation.get('budget') or {})}")
        add("wave1_instruments_preserved", "instruments" in observation,
            "wave1 keeps its public instrument feedback")
    return checks


def check_frequency_semantics(case, instruction):
    """Task b: per-wave clock + native finish semantics, no cross-wave conversion."""
    checks = []
    hz = 240.0 if case.wave == "wave1" else 120.0
    expected_dt = 1.0 / hz
    physics = instruction.get("physics") or {}
    finish = instruction.get("finish") or {}

    def add(name, ok, detail=""):
        checks.append(Check(name, ok, detail))

    add("wave_clock", approx(physics.get("step_seconds"), expected_dt, 1e-12),
        f"{case.wave} dt={physics.get('step_seconds')!r} expected={expected_dt!r}")
    add("wave_frequency", approx(physics.get("frequency_hz"), hz, 1e-9),
        f"{case.wave} hz={physics.get('frequency_hz')!r} expected={hz!r}")
    expected_finish = 720 if case.wave == "wave1" else 0
    add("wave_finish_extra_steps", finish.get("extra_physics_steps") == expected_finish,
        f"{case.wave} finish extra={finish.get('extra_physics_steps')!r} expected={expected_finish}")
    add("no_cross_wave_dt", not approx(physics.get("step_seconds"), 1.0 / (240 if hz == 120 else 120), 1e-9),
        "instruction must not expose the other wave's dt")
    return checks


def check_joint_order_mapping(case):
    """Task c: canonical joint order/count and native<->canonical arm mapping."""
    checks = []
    adapter = case.make_adapter()
    instruction = adapter.instruction()
    observation = adapter.observation(case.raw_observation)

    def add(name, ok, detail=""):
        checks.append(Check(name, ok, detail))

    joint_count = ARM_JOINT_COUNT[case.robot]
    raw_arms = case.raw_instruction.get("arms") or case.raw_instruction.get("actions", {}).get("arms") or {}
    for canonical_name, spec in instruction["arms"].items():
        native_name = adapter.reverse[canonical_name]
        raw_item = raw_arms.get(native_name) or {}
        raw_names = raw_item.get("arm_joint_names") or raw_item.get("joint_names")
        add(f"arm[{canonical_name}].count", len(spec["joint_names"]) == joint_count,
            f"count={len(spec['joint_names'])} expected={joint_count}")
        add(f"arm[{canonical_name}].order_from_native",
            raw_names == spec["joint_names"],
            f"canonical={spec['joint_names']!r} native={raw_names!r}")
        proprio = observation["proprioception"][canonical_name]
        add(f"proprio[{canonical_name}].order_matches_instruction",
            proprio["arm_joint_names"] == spec["joint_names"],
            f"proprio={proprio['arm_joint_names']!r}")

    # Canonical action round-trip: policy speaks canonical names, adapter speaks native.
    action_arms = {}
    for canonical_name, spec in instruction["arms"].items():
        positions = list(observation["proprioception"][canonical_name]["arm_joint_positions"])
        action_arms[canonical_name] = {"positions": positions, "gripper_width_m": 0.0}
    converted = adapter.action({"arms": action_arms, "steps": 1})
    expected_native = {adapter.reverse[name]: None for name in action_arms}
    add("action_roundtrip_native_arm_names", set(converted["arms"]) == set(expected_native),
        f"converted={sorted(converted['arms'])} expected={sorted(expected_native)}")
    if case.wave == "wave2" and case.robot == "piper-dual":
        add("wave2_piper_native_arm_maps_to_left",
            adapter.arm_map.get("arm") == "left" and "left" in instruction["arms"],
            f"arm_map={adapter.arm_map!r}")
    else:
        expected_map = {"arm": "arm"} if case.robot == "franka" else {"left": "left", "right": "right"}
        add("arm_map_identity", adapter.arm_map == expected_map, f"arm_map={adapter.arm_map!r}")
    return checks


def check_observation_gripper_ranges(case, instruction):
    checks = []
    adapter = case.make_adapter()
    raw_obs = case.raw_observation["proprioception"]
    for canonical_name, spec in instruction["arms"].items():
        native_name = adapter.reverse[canonical_name]
        raw_width = float(raw_obs[native_name]["gripper_width_m"])
        lo, hi = spec["gripper_width_m"]
        checks.append(
            Check(
                f"proprio[{canonical_name}].gripper_width_in_public_range",
                lo - 1e-6 <= raw_width <= hi + 1e-6,
                f"width={raw_width:.6f} range=[{lo}, {hi}]",
                severity="warn",
            )
        )
    return checks


# ----------------------------------------------------------------------------------
# Action boundary matrix (official Adapter behaviour, independent of the policy)
# ----------------------------------------------------------------------------------
def check_adapter_action_boundary(case):
    """Exercise the official adapter accept/reject matrix for one case."""
    checks = []
    adapter = case.make_adapter()
    instruction = adapter.instruction()
    observation = adapter.observation(case.raw_observation)
    ContractError = None
    try:
        from lab_sdk.adapters import ContractError as _CE  # type: ignore
        ContractError = _CE
    except Exception:  # pragma: no cover - fixture loader already imported it
        ContractError = ValueError

    arm_name = sorted(instruction["arms"])[0]
    joint_count = ARM_JOINT_COUNT[case.robot]
    current = list(observation["proprioception"][arm_name]["arm_joint_positions"])
    limit_hi = float(instruction["arms"][arm_name]["gripper_width_m"][1])

    def expect_accept(name, action):
        try:
            adapter.action(action)
            checks.append(Check(name, True, f"accepted: {json.dumps(action, default=repr)[:160]}"))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check(name, False, f"unexpected reject: {type(exc).__name__}: {exc}"))

    def expect_reject(name, action):
        try:
            adapter.action(action)
            checks.append(Check(name, False, f"unexpected accept: {json.dumps(action, default=repr)[:160]}"))
        except Exception as exc:  # noqa: BLE001
            checks.append(Check(name, True, f"rejected as expected: {type(exc).__name__}: {exc}"))

    expect_accept("action_finish_exact", {"finish": True})
    expect_accept("action_step_default", {"arms": {}, "steps": 1})
    expect_accept("action_step_max", {"arms": {}, "steps": 120})
    expect_accept(
        "action_full_arm_command",
        {
            "arms": {
                arm_name: {"positions": current, "gripper_width_m": round(limit_hi / 2.0, 6)}
            },
            "steps": 12,
        },
    )
    expect_reject("action_finish_false", {"finish": False})
    expect_reject("action_finish_nonbool", {"finish": 1})
    expect_reject("action_steps_zero", {"arms": {}, "steps": 0})
    expect_reject("action_steps_too_many", {"arms": {}, "steps": 121})
    expect_reject("action_steps_float", {"arms": {}, "steps": 1.5})
    expect_reject("action_unknown_field", {"jump": True})
    expect_reject("action_unknown_arm", {"arms": {"mystery_arm": {"positions": [0.0] * joint_count}}, "steps": 1})
    expect_reject(
        "action_wrong_joint_count",
        {"arms": {arm_name: {"positions": current[: joint_count - 1]}}, "steps": 1},
    )
    bad = list(current)
    bad[0] = float("nan")
    expect_reject("action_nonfinite_position", {"arms": {arm_name: {"positions": bad}}, "steps": 1})
    expect_reject(
        "action_gripper_out_of_range",
        {"arms": {arm_name: {"gripper_width_m": limit_hi + 0.01}}, "steps": 1},
    )
    expect_reject(
        "action_unknown_command_field",
        {"arms": {arm_name: {"wrench": [0.0, 0.0, 0.0]}}, "steps": 1},
    )

    if case.wave == "wave2" and case.task_id == "C07":
        expect_accept(
            "action_instrument_read_valid",
            {"instrument": {"device": "competition_balance", "method": "read"}},
        )
        expect_accept(
            "action_instrument_tare_valid",
            {"instrument": {"device": "competition_balance", "method": "tare"}},
        )
        expect_reject(
            "action_instrument_unknown_method",
            {"instrument": {"device": "competition_balance", "method": "calibrate"}},
        )
        expect_reject(
            "action_instrument_mixed_with_arm",
            {
                "instrument": {"device": "competition_balance", "method": "read"},
                "arms": {},
                "steps": 1,
            },
        )
    else:
        expect_reject(
            "action_instrument_not_allowed",
            {"instrument": {"device": "competition_balance", "method": "read"}},
        )
    return checks


# ----------------------------------------------------------------------------------
# Episode-level checks
# ----------------------------------------------------------------------------------
def evaluate_full_episode(case, result, rules, *, required_hold_seconds=1.2):
    """Task a/d checks: legal, budgeted, finish-terminated protocol episode."""
    checks = []
    limits = case_budget_limits(rules, case)
    dt = limits["dt"]

    def add(name, ok, detail="", severity="fail"):
        checks.append(Check(name, ok, detail, severity))

    add("finished_with_legal_finish", result.finished, f"cap_reason={result.cap_reason!r}")
    add("no_driver_violations", not result.violations,
        f"violations={[v['code'] for v in result.violations]}")
    add("waves_episode_finished", result.cap_reason == "finish",
        f"cap_reason={result.cap_reason!r}")
    stats = result.stats or {}
    add("all_action_steps_in_range",
        all(1 <= int(value) <= 120 for value in result.step_values),
        f"step values observed={stats.get('distinct_steps_values')}")

    budget = result.budget or {}
    add("budget_physics_steps",
        int(budget.get("physics_steps_used", 0)) <= int(limits["max_physics_steps"]),
        f"{budget.get('physics_steps_used')} <= {limits['max_physics_steps']}")
    add("budget_api_calls",
        int(budget.get("api_calls_used", 0)) <= int(limits["max_api_calls"]),
        f"{budget.get('api_calls_used')} <= {limits['max_api_calls']} "
        f"(unique requests={budget.get('unique_mutating_requests')}, "
        f"total requests={budget.get('total_mutating_requests')})")
    add("no_policy_exceptions", result.exception is None,
        (result.exception or "").splitlines()[0] if result.exception else "")
    add("policy_cpu_within_budget",
        float(result.policy_cpu_seconds or 0.0) <= float(limits["policy_cpu_seconds"]),
        f"{result.policy_cpu_seconds:.3f}s <= {limits['policy_cpu_seconds']}s")

    finish_steps = int(stats.get("finish_extra_physics_steps", -1))
    add("finish_extra_physics_steps",
        finish_steps == int(limits["finish_extra_steps"]),
        f"driver accounted {finish_steps} native finish steps")
    if case.wave == "wave1":
        # Task d: wave1 does not need policy-side waiting, the native finish holds 720 steps.
        add("wave1_finish_adds_native_hold", finish_steps == 720, f"value={finish_steps}")
        add("wave1_no_duplicate_finish_wait",
            int(stats.get("terminal_hold_steps", 0)) <= 720,
            f"policy-side trailing hold={stats.get('terminal_hold_steps')} steps (720 already added by finish)",
            severity="warn")
    else:
        required_steps = int(math.ceil(required_hold_seconds / dt - 1e-9))
        add("wave2_finish_adds_no_physics_steps", finish_steps == 0, f"value={finish_steps}")
        add("wave2_hold_steps_before_finish",
            int(stats.get("terminal_hold_steps", 0)) >= required_steps,
            f"terminal hold={stats.get('terminal_hold_steps')} steps "
            f"({stats.get('terminal_hold_seconds')}s) required>={required_steps} steps")
        last_actions = result.last_actions or []
        step_before_finish = any(
            entry.get("kind") == "step" and int((entry.get("canonical_action") or {}).get("steps", 0)) > 0
            for entry in last_actions[:-1][-3:]
        )
        add("wave2_finish_preceded_by_steps_action", step_before_finish,
            f"last actions={[e.get('kind') for e in last_actions[-4:]]}")
    return checks


def check_determinism(result_a, result_b):
    checks = []

    def add(name, ok, detail=""):
        checks.append(Check(name, ok, detail))

    add("deterministic_action_digest",
        result_a.action_digest == result_b.action_digest,
        f"{result_a.action_digest} vs {result_b.action_digest}")
    add("deterministic_outcome",
        result_a.finished == result_b.finished and result_a.cap_reason == result_b.cap_reason,
        f"a=({result_a.finished},{result_a.cap_reason}) b=({result_b.finished},{result_b.cap_reason})")
    add("deterministic_budget_usage",
        int(result_a.stats.get("physics_steps_tracked", -1)) == int(result_b.stats.get("physics_steps_tracked", -2))
        and int(result_a.stats.get("act_calls", -1)) == int(result_b.stats.get("act_calls", -2)),
        f"a steps/calls={result_a.stats.get('physics_steps_tracked')}/{result_a.stats.get('act_calls')} "
        f"b={result_b.stats.get('physics_steps_tracked')}/{result_b.stats.get('act_calls')}")
    return checks


# ----------------------------------------------------------------------------------
# C07 balance/tare protocol checks
# ----------------------------------------------------------------------------------
C07_NET_MASS_MIN_G = 9.5
C07_NET_MASS_MAX_G = 10.5


def _receipt_valid_mass(receipt):
    if not isinstance(receipt, dict) or receipt.get("ok") is not True:
        return None
    stable = receipt.get("stable") is True or str(receipt.get("status", "")).upper() == "STABLE"
    if not stable:
        return None
    net = receipt.get("net_mass_g")
    if isinstance(net, bool) or not isinstance(net, (int, float)):
        return None
    if not math.isfinite(float(net)):
        return None
    return float(net)


def _action_sequence(result):
    return list(result.action_log or [])


def _iter_actions_with_index(result):
    for position, entry in enumerate(_action_sequence(result)):
        yield position, entry


def _instrument_method(entry):
    return ((entry.get("canonical_action") or {}).get("instrument") or {}).get("method")


def _receipt_is_stable_ok(receipt):
    if not isinstance(receipt, dict) or receipt.get("ok") is not True:
        return False
    return receipt.get("stable") is True or str(receipt.get("status", "")).upper() == "STABLE"


def check_c07_nominal(result, *, case=None):
    """Task e: stable-gated single tare, read-confirmed net mass, no mixing."""
    checks = []

    def add(name, ok, detail="", severity="fail"):
        checks.append(Check(name, ok, detail, severity))

    balance = result.balance or {}
    events = result.instrument_events
    tare_events = [e for e in events if e.method == "tare"]
    read_events = [e for e in events if e.method == "read"]

    add("c07_finished", result.finished, f"cap_reason={result.cap_reason!r}")
    add("c07_no_driver_violations", not result.violations,
        f"violations={result.violation_codes()}")
    add("c07_balance_stub_present", bool(balance.get("synthetic")),
        "balance receipts are scripted protocol stubs, not real measurements")
    add("c07_tare_exactly_once", int(balance.get("tare_attempts", 0)) == 1,
        f"tare_attempts={balance.get('tare_attempts')}")
    add("c07_single_valid_tare", int(balance.get("valid_tare_count", 0)) == 1,
        f"valid_tare_count={balance.get('valid_tare_count')}")
    add("c07_no_tare_before_stable",
        "tare_before_stable" not in result.violation_codes()
        and "tare_before_pan_load" not in result.violation_codes(),
        f"violations={result.violation_codes()}")
    add("c07_no_second_tare_after_valid",
        int(balance.get("second_tare_attempts", 0)) == 0
        and "second_tare_after_valid" not in result.violation_codes(),
        f"second_tare_attempts={balance.get('second_tare_attempts')}")
    add("c07_instrument_not_mixed_with_arms",
        "instrument_mixed_with_arm_action" not in result.violation_codes(),
        f"violations={result.violation_codes()}")

    seq = _action_sequence(result)
    tare_positions = [
        pos for pos, entry in enumerate(seq)
        if entry.get("kind") == "instrument" and _instrument_method(entry) == "tare"
    ]
    first_tare_position = tare_positions[0] if tare_positions else None

    # (a) at least one valid stable read before the first tare; its mass may be
    # null before tare (only the stability flag matters at that point).
    stable_read_positions = []
    hold_steps_before_tare = 0
    if first_tare_position is not None:
        for pos in range(first_tare_position):
            entry = seq[pos]
            if entry.get("kind") == "instrument" and _instrument_method(entry) == "read":
                if _receipt_is_stable_ok(entry.get("receipt")):
                    stable_read_positions.append(pos)
            elif entry.get("kind") == "step":
                steps = int((entry.get("canonical_action") or {}).get("steps") or 0)
                if entry.get("moved"):
                    hold_steps_before_tare = 0
                else:
                    hold_steps_before_tare += steps
    required_hold_steps = 120  # >= 1.0 s at the wave2 120 Hz clock (C07 is wave2)
    add("c07_valid_stable_read_before_tare", bool(stable_read_positions),
        "needs >=1 read receipt with ok=True and stable/status STABLE before first tare;"
        f" stable read positions={stable_read_positions}")
    add("c07_hold_steps_before_tare", hold_steps_before_tare >= required_hold_steps,
        f"hold steps since the last robot motion before first tare={hold_steps_before_tare}"
        f" required>={required_hold_steps} (>=1 s)")

    # (b) reads after the valid tare must confirm the net mass near 10 g.
    valid_reads_after_tare = []
    for event in read_events:
        net = _receipt_valid_mass(event.receipt)
        if net is not None:
            valid_reads_after_tare.append((event, net))
    add("c07_reads_after_valid_tare", len(valid_reads_after_tare) >= 1,
        f"valid stable net-mass reads={len(valid_reads_after_tare)}")
    if valid_reads_after_tare:
        final_event, final_net = valid_reads_after_tare[-1]
        add("c07_final_net_mass_in_tolerance",
            C07_NET_MASS_MIN_G <= final_net <= C07_NET_MASS_MAX_G,
            f"final net_mass_g={final_net:.6f} expected [{C07_NET_MASS_MIN_G}, {C07_NET_MASS_MAX_G}]")
        add("c07_net_mass_read_used", True,
            f"last stable read net_mass_g={final_net:.6f},"
            f" tare_version={final_event.receipt.get('tare_version')}")
    else:
        add("c07_final_net_mass_in_tolerance", False,
            "no valid (ok, stable, numeric net_mass_g) read after the tare")
        add("c07_net_mass_read_used", False, "policy never received a usable net-mass reading")

    # (c) finish must follow the final read/measurement, not the tare itself.
    read_positions = [
        pos for pos, entry in enumerate(seq)
        if entry.get("kind") == "instrument" and _instrument_method(entry) == "read"
    ]
    if read_positions:
        last_read_position = read_positions[-1]
        tail = seq[last_read_position + 1:]
        add("c07_finish_after_read",
            bool(tail) and all(entry.get("kind") == "step" for entry in tail[:-1]) and tail[-1].get("kind") == "finish",
            f"tail kinds after last read={[entry.get('kind') for entry in tail]}")
    else:
        add("c07_finish_after_read", False, "policy never issued a read")
    return checks


def check_c07_abnormal(result, *, expect_recovery=True, case=None):
    """Task e: unstable / missing-field receipts must not be treated as valid mass."""
    checks = []

    def add(name, ok, detail="", severity="fail"):
        checks.append(Check(name, ok, detail, severity))

    balance = result.balance or {}
    events = result.instrument_events
    read_events = [e for e in events if e.method == "read"]
    abnormal_events = [
        e for e in read_events
        if not (isinstance(e.receipt, dict) and e.receipt.get("ok") is True
                and (e.receipt.get("stable") is True or str(e.receipt.get("status", "")).upper() == "STABLE")
                and _receipt_valid_mass(e.receipt) is not None)
    ]
    add("c07_abnormal_receipt_injected", len(abnormal_events) >= 1,
        f"abnormal read receipts={len(abnormal_events)} of {len(read_events)}")
    add("c07_single_valid_tare", int(balance.get("valid_tare_count", 0)) == 1,
        f"valid_tare_count={balance.get('valid_tare_count')}")
    add("c07_no_second_tare_after_valid", int(balance.get("second_tare_attempts", 0)) == 0,
        f"second_tare_attempts={balance.get('second_tare_attempts')}")

    seq = _action_sequence(result)
    if abnormal_events:
        first_abnormal = abnormal_events[0]
        # The receipt produced by iteration N is seen by the policy at act N+1.
        next_action = seq[first_abnormal.index] if first_abnormal.index < len(seq) else None
        add("c07_no_finish_on_abnormal_receipt",
            bool(next_action) and next_action.get("kind") != "finish",
            f"action after abnormal receipt={None if next_action is None else next_action.get('kind')}")
        add("c07_no_tare_on_abnormal_receipt",
            bool(next_action) and not (next_action.get("kind") == "instrument"
                                       and (next_action.get("canonical_action") or {}).get("instrument", {}).get("method") == "tare"),
            f"action after abnormal receipt={None if next_action is None else next_action.get('kind')}")
        # A subsequent read or step must happen before finishing (no silent success).
        later_actions = seq[first_abnormal.index + 1:]
        add("c07_continues_waiting_after_abnormal",
            any(entry.get("kind") in ("step", "instrument") for entry in later_actions)
            or (expect_recovery and result.finished),
            f"actions after abnormal={[e.get('kind') for e in later_actions[:5]]}")

    if expect_recovery:
        valid_reads = [e for e in read_events if _receipt_valid_mass(e.receipt) is not None]
        add("c07_recovers_to_valid_mass_read", bool(valid_reads),
            f"valid reads={len(valid_reads)}")
        if valid_reads:
            final_net = _receipt_valid_mass(valid_reads[-1].receipt)
            add("c07_final_net_mass_in_tolerance",
                C07_NET_MASS_MIN_G <= final_net <= C07_NET_MASS_MAX_G,
                f"final net_mass_g={final_net:.6f}")
        add("c07_finished_after_recovery", result.finished, f"cap_reason={result.cap_reason!r}")
        add("c07_no_driver_violations", not result.violations,
            f"violations={result.violation_codes()}")
    else:
        # Persistent-abnormality scenario: a safe abort is acceptable, but never a
        # success claim: zero valid net-mass readings and no second valid tare.
        valid_reads = [e for e in read_events if _receipt_valid_mass(e.receipt) is not None]
        add("c07_safe_abort_no_measured_success",
            not valid_reads,
            f"valid net-mass reads received={len(valid_reads)} (persistent abnormal stub)")
        add("c07_safe_abort_finished", result.finished, f"cap_reason={result.cap_reason!r}")
        add("c07_safe_abort_no_second_tare", int(balance.get("valid_tare_count", 0)) <= 1,
            f"valid_tare_count={balance.get('valid_tare_count')}")
        add("c07_safe_abort_no_driver_violations", not result.violations,
            f"violations={result.violation_codes()}")
    return checks


def check_c07_perception_unavailable(result):
    """Real C07 fixture without images: policy must safe-abort, not fake success."""
    checks = []

    def add(name, ok, detail="", severity="fail"):
        checks.append(Check(name, ok, detail, severity))

    balance = result.balance or {}
    add("c07_no_perception_safe_abort_finished", result.finished,
        f"cap_reason={result.cap_reason!r}")
    add("c07_no_perception_no_driver_violations", not result.violations,
        f"violations={result.violation_codes()}")
    add("c07_no_perception_no_tare_without_evidence",
        int(balance.get("tare_attempts", 0)) == 0,
        f"tare_attempts={balance.get('tare_attempts')} (no camera/balance evidence offline)")
    add("c07_no_perception_no_success_claim",
        int(balance.get("valid_tare_count", 0)) == 0,
        "no valid tare without perception evidence")
    add("c07_no_perception_hold_before_finish",
        int((result.stats or {}).get("terminal_hold_steps", 0)) >= 1,
        f"terminal hold steps={(result.stats or {}).get('terminal_hold_steps')}")
    return checks


# ----------------------------------------------------------------------------------
# Policy source / submission checks
# ----------------------------------------------------------------------------------
_SUBMISSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


_PRIVATE_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+[^\n]*\b(judge|truth|private|referee)\b", re.IGNORECASE
)


def check_policy_submission(policy_dir, policy_source="policy.py"):
    checks = []

    def add(name, ok, detail="", severity="fail"):
        checks.append(Check(name, ok, detail, severity))

    policy_dir = Path(policy_dir)
    entry = policy_dir / policy_source
    add("policy_entrypoint_exists", entry.is_file(), f"path={entry}")
    submission_path = policy_dir / "submission.json"
    add("policy_submission_json_exists", submission_path.is_file(), f"path={submission_path}")
    if submission_path.is_file():
        try:
            submission = json.loads(submission_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            add("policy_submission_json_parses", False, f"{type(exc).__name__}: {exc}")
            submission = {}
        add("policy_submission_json_parses", bool(submission), f"keys={sorted(submission)}")
        add("policy_submission_schema", submission.get("schema") == "lab-submission/v2",
            f"schema={submission.get('schema')!r}")
        add("policy_submission_interface", submission.get("interface") == "lab-policy-v2",
            f"interface={submission.get('interface')!r}")
        add("policy_submission_entrypoint_matches",
            submission.get("entrypoint") == policy_source,
            f"entrypoint={submission.get('entrypoint')!r} expected={policy_source!r}")
        submission_id = submission.get("submission_id")
        add("policy_submission_id",
            isinstance(submission_id, str)
            and bool(_SUBMISSION_ID_RE.match(submission_id))
            and any(ch.isalnum() for ch in submission_id),
            f"submission_id={submission_id!r}")
    private_imports = []
    if policy_dir.is_dir():
        for path in policy_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if _PRIVATE_IMPORT_RE.search(line):
                    private_imports.append(
                        {"file": str(path.relative_to(policy_dir)), "line": line_number, "code": line.strip()[:120]}
                    )
    add("policy_no_private_judge_imports", not private_imports,
        f"private import candidates={private_imports[:6]}" if private_imports
        else "no judge/truth/private module imports found")
    return checks


_HARD_FREQUENCY_PATTERNS = (
    (re.compile(r"\*\s*240\b"), "seconds-to-wave1-steps multiplication"),
    (re.compile(r"\b240\s*\*"), "wave1-steps-to-seconds multiplication"),
    (re.compile(r"\b1\s*/\s*240\b"), "hardcoded wave1 dt"),
    (re.compile(r"0\.00416[0-9]*"), "hardcoded wave1 dt literal"),
)
_SOFT_FREQUENCY_TOKENS = ("240", "43200", "0.00416")


def scan_policy_frequency_hardcode(policy_dir, policy_source="policy.py", max_files=64):
    """Heuristic scan for cross-wave hardcoded step counts.

    The dynamic episode behaviour is authoritative; this scan only flags source
    lines such as ``seconds * 240`` that would silently assume one wave's clock.
    """
    policy_dir = Path(policy_dir)
    files = []
    hard = []
    soft = []
    scanned = 0
    for path in sorted(policy_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        if scanned > max_files:
            break
        files.append(str(path.relative_to(policy_dir)))
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            code = raw_line.split("#", 1)[0]
            for pattern, label in _HARD_FREQUENCY_PATTERNS:
                if pattern.search(code):
                    hard.append({"file": files[-1], "line": line_number, "label": label, "code": stripped[:160]})
            for token in _SOFT_FREQUENCY_TOKENS:
                if re.search(rf"(?<![\d.]){re.escape(token)}(?![\d.])", code):
                    soft.append({"file": files[-1], "line": line_number, "token": token, "code": stripped[:160]})
    return {"scanned_files": files, "hard_matches": hard, "soft_matches": soft}


def check_policy_frequency_source(scan):
    checks = []

    def add(name, ok, detail="", severity="fail"):
        checks.append(Check(name, ok, detail, severity))

    add("policy_source_scanned", bool(scan.get("scanned_files")),
        f"files={scan.get('scanned_files')}")
    hard = scan.get("hard_matches") or []
    add("policy_no_wave_step_conversion_hardcode", not hard,
        f"hard matches={hard[:6]}" if hard else "no seconds<->240Hz conversion literals found")
    soft = scan.get("soft_matches") or []
    add("policy_frequency_literals_reviewed", not soft,
        f"{len(soft)} frequency/budget literal occurrence(s) need review: {soft[:6]}",
        severity="warn")
    return checks


def aggregate_checks(checks):
    failed = [c for c in checks if not c.ok and c.severity == "fail"]
    warned = [c for c in checks if not c.ok and c.severity == "warn"]
    return {
        "total": len(checks),
        "failed": len(failed),
        "warned": len(warned),
        "passed": len(checks) - len(failed) - len(warned),
        "ok": not failed,
    }
