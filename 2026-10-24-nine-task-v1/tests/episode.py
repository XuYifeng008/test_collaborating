"""Offline episode driver: runs the submitted ``Policy`` against canonical SDK v2
instructions/observations produced by ``lab_sdk.adapters.Adapter`` from the public
recorded samples (or protocol-synthetic derivations of them).

Design notes / limits (reported in TEST_RESULTS.md as well):

* This is a *protocol harness*, not a simulator. Physics time advances by
  ``steps * step_seconds``; joint feedback is slewed toward the last commanded
  targets using the published per-joint speed limits. TCP positions, images,
  objects, contact and judge truth are NOT simulated (they are absent from the
  public fixtures anyway).
* Budgets are tracked by the driver because wave 2 observations do not expose
  remaining steps/calls. Wave 1: observations and actions each consume one API
  call, the native finish holds ``extra_physics_steps`` (720). Wave 2: mutating
  requests (step/finish/instrument) share the 10000-request budget, observations
  are free, and finish adds 0 physics steps.
* C07 balance receipts are scripted protocol stubs (``FakeBalance``), clearly
  synthetic: they are used to exercise the tare/read state machine only. No real
  mass measurement, flow or liquid physics is claimed.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from fixtures import case_budget_limits, ensure_sdk_importable

try:  # NumPy is required by the policy under test (runtime profile pins 1.26.4)
    import numpy as np
except Exception:  # pragma: no cover - fixtures tests report this as SKIP
    np = None

MAX_STEPS_PER_ACTION = 120

VIOLATION_CODES = (
    "policy_load_exception",
    "policy_constructor_exception",
    "reset_exception",
    "act_exception",
    "invalid_action",
    "unknown_action_type",
    "instrument_mixed_with_arm_action",
    "instrument_not_allowed",
    "budget_steps_exceeded",
    "budget_calls_exceeded",
    "budget_requests_exceeded",
    "loop_guard",
    "wall_clock_guard",
    "policy_cpu_budget_exceeded",
    "no_finish",
    "tare_before_stable",
    "tare_before_pan_load",
    "second_tare_after_valid",
)


# ----------------------------------------------------------------------------------
# Policy loading
# ----------------------------------------------------------------------------------
class PolicyLoadError(RuntimeError):
    pass


def _purge_modules_from_dir(directory):
    """Drop previously imported modules whose file lives under ``directory``."""
    target = str(Path(directory).resolve()) + os.sep
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        try:
            resolved = str(Path(filename).resolve())
        except OSError:
            continue
        if resolved.startswith(target):
            sys.modules.pop(name, None)


def load_policy_module(policy_dir, policy_source="policy.py", *, fresh=True):
    """Import ``<policy_dir>/<policy_source>`` and return the module.

    The policy directory is placed on ``sys.path`` so sibling modules
    (kinematics/vision/skills/...) import exactly like they do from the packaged
    submission. With ``fresh=True`` every episode re-executes the entry module and
    any sibling modules previously loaded from that directory, mirroring the
    "new policy process per replica" contract and keeping determinism honest.
    """
    policy_dir = Path(policy_dir).resolve()
    entry = policy_dir / policy_source
    if not entry.is_file():
        raise PolicyLoadError(f"policy source not found: {entry}")
    if fresh:
        _purge_modules_from_dir(policy_dir)
    if str(policy_dir) not in sys.path:
        sys.path.insert(0, str(policy_dir))
    module_name = "my_policy_under_test"
    spec = importlib.util.spec_from_file_location(module_name, entry)
    if spec is None or spec.loader is None:
        raise PolicyLoadError(f"cannot build import spec for {entry}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_policy_class(policy_dir, policy_source="policy.py", *, fresh=True):
    module = load_policy_module(policy_dir, policy_source, fresh=fresh)
    policy_cls = getattr(module, "Policy", None)
    if policy_cls is None or not callable(policy_cls):
        raise PolicyLoadError(
            f"{Path(policy_dir) / policy_source} does not define a callable class Policy"
        )
    return policy_cls


def make_file_policy_factory(policy_dir, policy_source="policy.py", module_patch=None):
    """Return a zero-arg factory producing a fresh ``Policy`` instance.

    ``module_patch`` is called with the freshly imported module before
    instantiation; the C07 perception tests use it to inject a synthetic
    ``perceive`` implementation instead of touching the policy source.
    """

    def factory():
        module = load_policy_module(policy_dir, policy_source, fresh=True)
        if module_patch is not None:
            module_patch(module)
        policy_cls = getattr(module, "Policy", None)
        if policy_cls is None or not callable(policy_cls):
            raise PolicyLoadError(
                f"{Path(policy_dir) / policy_source} does not define a callable class Policy"
            )
        return policy_cls()

    return factory


# ----------------------------------------------------------------------------------
# Budget tracking
# ----------------------------------------------------------------------------------
class BudgetTracker:
    def __init__(self, wave, limits):
        self.wave = wave
        self.max_physics_steps = int(limits["max_physics_steps"])
        self.max_api_calls = int(limits["max_api_calls"])
        self.finish_extra_steps = int(limits["finish_extra_steps"])
        self.dt = float(limits["dt"])
        self.observation_calls = 0
        self.action_calls = 0
        self.total_requests = 0
        self._request_signatures = set()
        self.physics_steps = 0
        self.instrument_calls = 0
        self.finish_calls = 0

    # -- accounting ---------------------------------------------------------------
    def observe(self):
        self.observation_calls += 1

    def _record_request(self, raw_action):
        self.total_requests += 1
        try:
            signature = json.dumps(
                raw_action, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=repr
            )
        except (TypeError, ValueError):
            signature = repr(raw_action)
        self._request_signatures.add(signature)

    def record_step(self, raw_action, steps):
        self.action_calls += 1
        self._record_request(raw_action)
        self.physics_steps += int(steps)

    def record_finish(self, raw_action):
        self.action_calls += 1
        self._record_request(raw_action)
        self.finish_calls += 1
        self.physics_steps += self.finish_extra_steps

    def record_instrument(self, raw_action):
        self.action_calls += 1
        self._record_request(raw_action)
        self.instrument_calls += 1

    # -- limits -------------------------------------------------------------------
    @property
    def unique_requests(self):
        return len(self._request_signatures)

    def calls_used(self):
        """Wave 1 counts observations and actions as API calls."""
        return self.observation_calls + self.action_calls

    def exceeded(self):
        codes = []
        if self.physics_steps > self.max_physics_steps:
            codes.append("budget_steps_exceeded")
        if self.wave == "wave1":
            if self.calls_used() > self.max_api_calls:
                codes.append("budget_calls_exceeded")
        else:
            if self.unique_requests > self.max_api_calls:
                codes.append("budget_requests_exceeded")
        return codes

    def snapshot(self):
        remaining_steps = max(0, self.max_physics_steps - self.physics_steps)
        if self.wave == "wave1":
            remaining_calls = max(0, self.max_api_calls - self.calls_used())
        else:
            remaining_calls = max(0, self.max_api_calls - self.unique_requests)
        return {
            "wave": self.wave,
            "physics_steps_used": self.physics_steps,
            "max_physics_steps": self.max_physics_steps,
            "remaining_physics_steps": remaining_steps,
            "observation_calls": self.observation_calls,
            "action_calls": self.action_calls,
            "total_mutating_requests": self.total_requests,
            "unique_mutating_requests": self.unique_requests,
            "max_api_calls": self.max_api_calls,
            "api_calls_used": self.calls_used() if self.wave == "wave1" else self.unique_requests,
            "remaining_api_calls": remaining_calls,
            "instrument_calls": self.instrument_calls,
            "finish_calls": self.finish_calls,
        }


# ----------------------------------------------------------------------------------
# Protocol-level forward kinematics (public robot_kinematics only)
# ----------------------------------------------------------------------------------
def _axis_angle_4x4(axis, angle):
    a = [float(v) for v in axis]
    norm = math.sqrt(sum(v * v for v in a))
    if norm < 1e-12:
        return np.eye(4)
    x, y, z = [v / norm for v in a]
    c, s = math.cos(angle), math.sin(angle)
    C = 1.0 - c
    R = np.array(
        [
            [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
        ],
        dtype=float,
    )
    T = np.eye(4)
    T[:3, :3] = R
    return T


def _translation_4x4(axis, distance):
    T = np.eye(4)
    T[:3, 3] = np.asarray(axis, dtype=float).reshape(3) * float(distance)
    return T


def _matrix_to_quaternion_wxyz(R):
    """Rotation matrix -> (w, x, y, z) unit quaternion (Shepperd's method)."""
    R = np.asarray(R, dtype=float)
    trace = float(np.trace(R))
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z], dtype=float)
    norm = float(np.linalg.norm(q))
    return (q / norm).tolist() if norm > 1e-12 else [1.0, 0.0, 0.0, 0.0]


class ArmForwardKinematics:
    """FK from the published per-arm kinematic chain (same public convention).

    The tool transform constant is calibrated once from the recorded public
    observation so the harness feedback is self-consistent with the policy's own
    run-time calibrated model (both derive it from the same first observation).
    """

    def __init__(self, kin):
        self.base = np.asarray(kin["base_matrix"], dtype=float)
        self.joints = list(kin["joints"])
        self.arm_names = [str(name) for name in (kin.get("arm_names") or [])]
        self._q_index = {name: i for i, name in enumerate(self.arm_names)}
        self._local0 = [np.asarray(j["local0"], dtype=float) for j in self.joints]
        self._local1_inv = [np.linalg.inv(np.asarray(j["local1"], dtype=float)) for j in self.joints]
        self._axis = [np.asarray(j["axis"], dtype=float).reshape(3) for j in self.joints]
        self._kind = [j.get("kind") for j in self.joints]
        self._qpos = [self._q_index.get(str(j.get("name"))) for j in self.joints]
        self.tool_R = np.eye(3)
        self.tool_t = np.zeros(3)
        self.calibrated = False

    def raw(self, q):
        T = self.base.copy()
        for k in range(len(self.joints)):
            qi = self._qpos[k]
            angle = 0.0 if qi is None or qi >= len(q) else float(q[qi])
            kind = self._kind[k]
            if kind == "revolute":
                step = _axis_angle_4x4(self._axis[k], angle)
            elif kind == "prismatic":
                step = _translation_4x4(self._axis[k], angle)
            else:
                step = np.eye(4)
            T = T @ self._local0[k] @ step @ self._local1_inv[k]
        return T[:3, :3].copy(), T[:3, 3].copy()

    def calibrate_tool(self, q0, tcp_position_m, tcp_rotation_world):
        Rc, pc = self.raw(q0)
        Rt = np.asarray(tcp_rotation_world, dtype=float).reshape(3, 3)
        pt = np.asarray(tcp_position_m, dtype=float).reshape(3)
        self.tool_R = Rc.T @ Rt
        self.tool_t = Rc.T @ (pt - pc)
        self.calibrated = True
        return self

    def tcp(self, q):
        Rc, pc = self.raw(q)
        if not self.calibrated:
            return Rc, pc
        return Rc @ self.tool_R, pc + Rc @ self.tool_t


# ----------------------------------------------------------------------------------
# Simple joint/gripper plant (protocol-level feedback only; no simulator)
# ----------------------------------------------------------------------------------
class PlantState:
    """Kinematic feedback mock (explicitly NOT physics/simulation).

    Each ``arms`` command is written straight back into the observation:
    measured joint positions = commanded positions, measured gripper width =
    commanded width (with an optional synthetic "grasped object" stall), and the
    measured TCP pose is recomputed with forward kinematics from the *public*
    ``robot_kinematics`` contract.  The tool transform constant is calibrated
    once from the first public observation, exactly like the policy does, so the
    public-observation servo loops are self-consistent.  No object pose, contact
    physics, image or judge truth is simulated.
    """

    def __init__(self, adapter, instruction, raw_observation):
        if np is None:
            raise RuntimeError("NumPy is required for the offline FK plant")
        self.adapter = adapter
        self.instruction = instruction
        self.template = copy.deepcopy(raw_observation["proprioception"])
        self.arms = {}
        for canonical_name, spec in (instruction.get("arms") or {}).items():
            native_name = adapter.reverse[canonical_name]
            item = self.template[native_name]
            names = list(item.get("joint_names") or [])
            joint_positions = list(item.get("joint_positions") or [])
            index = {name: i for i, name in enumerate(names)}
            q = []
            for name in spec["joint_names"]:
                if name not in index:
                    raise RuntimeError(f"fixture proprioception lacks joint {name!r}")
                q.append(float(joint_positions[index[name]]))
            kin = (instruction.get("robot_kinematics") or {}).get(canonical_name)
            if kin is None:
                raise RuntimeError(f"instruction lacks kinematics for arm {canonical_name!r}")
            fk = ArmForwardKinematics(kin)
            fk.calibrate_tool(q, item.get("tcp_position_m"), item.get("tcp_rotation_world"))
            self.arms[canonical_name] = {
                "native": native_name,
                "q": q,
                "width": float(item.get("gripper_width_m", 0.0) or 0.0),
                "fk": fk,
                "template": item,
            }
        self.last_motion = {"moved": False, "max_joint_delta": 0.0, "max_width_delta": 0.0}

    # -- observation feedback ------------------------------------------------------
    def _write_proprio_item(self, canonical_name, data):
        arms = self.arms[canonical_name]
        item = data[arms["native"]]
        q = arms["q"]
        width = float(arms["width"])
        names = list(item.get("joint_names") or [])
        arm_names = list(item.get("arm_joint_names") or [])
        positions = list(item.get("joint_positions") or [])
        index = {name: i for i, name in enumerate(names)}
        measured = {name: float(q[i]) for i, name in enumerate(arm_names) if i < len(q)}
        for name, value in measured.items():
            if name in index:
                positions[index[name]] = value
        # Finger joints keep the fixture's order/sign convention, filled from width.
        finger_names = [name for name in names if name not in measured]
        template_positions = list(arms["template"].get("joint_positions") or [])
        for i, name in enumerate(finger_names):
            idx = index.get(name)
            if idx is None:
                continue
            template_value = template_positions[idx] if idx < len(template_positions) else 0.0
            sign = -1.0 if float(template_value) < 0.0 else 1.0
            positions[idx] = sign * width / 2.0
        item["joint_positions"] = positions
        item["arm_joint_positions"] = [float(v) for v in q]
        item["joint_velocities"] = [0.0 for _ in positions]
        item["gripper_width_m"] = width
        R, p = arms["fk"].tcp(q)
        item["tcp_position_m"] = [float(v) for v in p]
        item["tcp_rotation_world"] = [[float(v) for v in row] for row in R]
        item["tcp_orientation_wxyz"] = _matrix_to_quaternion_wxyz(R)
        item["arm_speed_limit_rad_s"] = item.get("arm_speed_limit_rad_s", 0.8)
        item["gripper_width_speed_limit_m_s"] = item.get("gripper_width_speed_limit_m_s", 0.06)

    def snapshot(self):
        proprio = copy.deepcopy(self.template)
        for canonical_name in self.arms:
            self._write_proprio_item(canonical_name, proprio)
        return proprio

    # -- command application -------------------------------------------------------
    def apply(self, canonical_action, gripper_mock=None):
        arms_commands = canonical_action.get("arms") or {}
        before = {name: (list(arms["q"]), float(arms["width"])) for name, arms in self.arms.items()}
        for native_name, command in arms_commands.items():
            canonical_name = self.adapter.arm_map.get(native_name)
            if canonical_name is None or canonical_name not in self.arms:
                continue
            arms = self.arms[canonical_name]
            if "positions" in command:
                arms["q"] = [float(v) for v in command["positions"]]
            if "gripper_width_m" in command:
                target_width = float(command["gripper_width_m"])
                if gripper_mock is not None and target_width < float(gripper_mock["release_threshold_m"]):
                    # Synthetic grasp: fingers stop on an object instead of closing fully.
                    arms["width"] = float(gripper_mock["stall_width_m"])
                else:
                    arms["width"] = target_width
        max_joint_delta = 0.0
        max_width_delta = 0.0
        for canonical_name, (q_before, width_before) in before.items():
            arms = self.arms[canonical_name]
            max_joint_delta = max(
                max_joint_delta,
                max((abs(a - b) for a, b in zip(arms["q"], q_before)), default=0.0),
            )
            max_width_delta = max(max_width_delta, abs(arms["width"] - width_before))
        self.last_motion = {
            "moved": max_joint_delta > 1e-9 or max_width_delta > 1e-9,
            "max_joint_delta": max_joint_delta,
            "max_width_delta": max_width_delta,
        }
        return self.last_motion




# ----------------------------------------------------------------------------------
# C07 balabce stub (scripted protocol receipts; NOT a real balance)
# ----------------------------------------------------------------------------------
BALANCE_SCHEMA = "lab-instrument-result/v1"
BALANCE_DEVICE = "competition_balance"


@dataclass
class InstrumentEvent:
    index: int
    method: str
    sim_time: float
    stable_before_call: bool
    receipt: dict
    violations: list
    raw_action: dict

    def to_dict(self):
        return {
            "index": self.index,
            "method": self.method,
            "sim_time_s": round(self.sim_time, 6),
            "stable_before_call": self.stable_before_call,
            "receipt": copy.deepcopy(self.receipt),
            "violations": list(self.violations),
        }


class FakeBalance:
    """Scripted C07 balance stub.

    Modes:
      * ``nominal`` - stable once the robot has not moved for ``stable_window_s``
        (and the pan is assumed loaded after ``pan_load_after_s`` of physics time);
        tare is only valid when stable; liquid accumulates while a gripper is
        commanded closed, so ``read`` returns a monotone mass ramp capped at
        ``cap_mass_g`` (protocol stub only).
      * ``abnormal_unstable`` - the first read after the valid tare returns an
        unstable receipt without mass fields once, then nominal behaviour resumes.
      * ``abnormal_missing`` - same but the abnormal receipt is a malformed /
        missing-field receipt instead of an explicit UNSTABLE one.
      * ``abnormal_persistent`` - every read after the valid tare stays abnormal
        (the policy must safe-abort, never claim a measured 10 g success).

    The receipt schema is a synthetic test-harness contract (documented in
    TEST_RESULTS.md); it is not a public official format.
    """

    MODES = ("nominal", "abnormal_unstable", "abnormal_missing", "abnormal_persistent")

    def __init__(
        self,
        mode="nominal",
        dt=1.0 / 120.0,
        stable_window_s=1.0,
        pan_load_after_s=1.0,
        empty_cup_mass_g=85.0,
        pour_rate_g_s=2.0,
        cap_mass_g=10.1,
        closed_gripper_width_m=0.055,
    ):
        if mode not in self.MODES:
            raise ValueError(f"unknown FakeBalance mode: {mode!r}")
        self.mode = mode
        self.dt = float(dt)
        self.stable_window_s = float(stable_window_s)
        self.pan_load_after_steps = max(1, int(round(pan_load_after_s / self.dt)))
        self.empty_cup_mass_g = float(empty_cup_mass_g)
        self.pour_rate_g_s = float(pour_rate_g_s)
        self.cap_mass_g = float(cap_mass_g)
        self.closed_gripper_width_m = float(closed_gripper_width_m)

        self.physics_steps = 0
        self.pan_loaded = False
        self.last_motion_end_time = None
        self._commanded_widths = {}
        self.liquid_g = 0.0
        self.tare_version = 0
        self.tare_attempts = 0
        self.valid_tare_count = 0
        self.invalid_tare_attempts = 0
        self.second_tare_attempts = 0
        self.tare_offset_g = 0.0
        self.tare_time_s = None
        self.reads = 0
        self.reads_after_valid_tare = 0
        self.stable_reads_after_valid_tare = 0
        self.last_receipt = None
        self._abnormal_pending = mode in ("abnormal_unstable", "abnormal_missing")

    # -- state helpers ------------------------------------------------------------
    def is_stable(self, sim_time):
        if self.last_motion_end_time is None:
            return True
        return (sim_time - self.last_motion_end_time) >= self.stable_window_s

    @property
    def any_gripper_closed(self):
        return any(width <= self.closed_gripper_width_m for width in self._commanded_widths.values())

    def _gross_mass(self):
        if not self.pan_loaded:
            return 0.0
        return self.empty_cup_mass_g + self.liquid_g

    def _displayed_mass(self):
        gross = self._gross_mass()
        if self.tare_version >= 1:
            return gross - self.tare_offset_g
        return gross

    # -- per-step update ----------------------------------------------------------
    def notify_step(self, canonical_action, sim_time_after, moved):
        arms = canonical_action.get("arms") or {}
        for canonical_name, command in arms.items():
            if "gripper_width_m" in command:
                self._commanded_widths[canonical_name] = round(float(command["gripper_width_m"]), 12)
        steps = int(canonical_action.get("steps", 0))
        if moved:
            self.last_motion_end_time = sim_time_after
        self.physics_steps += steps
        if self.physics_steps >= self.pan_load_after_steps:
            self.pan_loaded = True
        if self.tare_version >= 1 and steps > 0 and self.any_gripper_closed:
            self.liquid_g = min(self.cap_mass_g, self.liquid_g + self.pour_rate_g_s * steps * self.dt)

    # -- action handling ----------------------------------------------------------
    def _base_receipt(self, method, sim_time):
        return {
            "schema": BALANCE_SCHEMA,
            "device": BALANCE_DEVICE,
            "method": method,
            "unit": "g",
            "tare_version": self.tare_version,
            "time_s": round(sim_time, 6),
        }

    def _ok_read_receipt(self, sim_time):
        receipt = self._base_receipt("read", sim_time)
        stable = self.is_stable(sim_time)
        displayed = self._displayed_mass()
        receipt.update(
            {
                "ok": True,
                "stable": stable,
                "status": "STABLE" if stable else "UNSTABLE",
                "mass_g": round(displayed, 6),
                "net_mass_g": round(displayed, 6) if self.tare_version >= 1 else None,
                "gross_mass_g": round(self._gross_mass(), 6),
                "tare_active": self.tare_version >= 1,
            }
        )
        return receipt

    def handle(self, method, sim_time):
        """Return (receipt, violation_codes)."""
        if method == "read":
            self.reads += 1
            if self.tare_version >= 1 and (self._abnormal_pending or self.mode == "abnormal_persistent"):
                if self.mode != "abnormal_persistent":
                    self._abnormal_pending = False
                self.last_receipt = self._abnormal_receipt(sim_time)
                return self.last_receipt, []
            receipt = self._ok_read_receipt(sim_time)
            if self.tare_version >= 1:
                self.reads_after_valid_tare += 1
                if receipt["stable"]:
                    self.stable_reads_after_valid_tare += 1
            self.last_receipt = receipt
            return receipt, []
        if method == "tare":
            self.tare_attempts += 1
            if self.tare_version >= 1:
                self.second_tare_attempts += 1
                receipt = self._base_receipt("tare", sim_time)
                receipt.update({"ok": False, "stable": self.is_stable(sim_time),
                                "status": "STABLE" if self.is_stable(sim_time) else "UNSTABLE",
                                "error": "tare_already_set"})
                self.last_receipt = receipt
                return receipt, ["second_tare_after_valid"]
            if not self.pan_loaded:
                self.last_receipt = self._invalid_tare_receipt(sim_time, "no_pan_load")
                return self.last_receipt, ["tare_before_pan_load"]
            if not self.is_stable(sim_time):
                self.last_receipt = self._invalid_tare_receipt(sim_time, "unstable")
                return self.last_receipt, ["tare_before_stable"]
            self.tare_version = 1
            self.valid_tare_count += 1
            self.tare_time_s = sim_time
            self.tare_offset_g = self._gross_mass()
            receipt = self._base_receipt("tare", sim_time)
            receipt.update({"ok": True, "stable": True, "status": "STABLE", "tare_active": True,
                            # the tare receipt is not a mass measurement; the policy must
                            # rely on later reads for the net mass (zero shown on display)
                            "mass_g": 0.0, "net_mass_g": 0.0})
            self.last_receipt = receipt
            return receipt, []
        raise ValueError(f"unknown balance method: {method!r}")

    def _invalid_tare_receipt(self, sim_time, error):
        receipt = self._base_receipt("tare", sim_time)
        stable = self.is_stable(sim_time)
        receipt.update({"ok": False, "stable": stable,
                        "status": "STABLE" if stable else "UNSTABLE", "error": error})
        return receipt

    def _abnormal_receipt(self, sim_time):
        if self.mode == "abnormal_missing":
            return {
                "schema": BALANCE_SCHEMA,
                "device": BALANCE_DEVICE,
                "method": "read",
                "ok": False,
                "error": "malformed_receipt",
                "time_s": round(sim_time, 6),
            }
        return {
            "schema": BALANCE_SCHEMA,
            "device": BALANCE_DEVICE,
            "method": "read",
            "unit": "g",
            "ok": False,
            "stable": False,
            "status": "UNSTABLE",
            "error": "unstable",
            "tare_version": self.tare_version,
            "time_s": round(sim_time, 6),
        }

    def summary(self):
        return {
            "mode": self.mode,
            "synthetic": True,
            "notice": "scripted protocol stub; not a real balance and no real mass/physics is claimed",
            "tare_version": self.tare_version,
            "tare_attempts": self.tare_attempts,
            "valid_tare_count": self.valid_tare_count,
            "invalid_tare_attempts": self.invalid_tare_attempts,
            "second_tare_attempts": self.second_tare_attempts,
            "reads": self.reads,
            "reads_after_valid_tare": self.reads_after_valid_tare,
            "stable_reads_after_valid_tare": self.stable_reads_after_valid_tare,
            "liquid_stub_g": round(self.liquid_g, 6),
            "pan_loaded_stub": self.pan_loaded,
            "tare_offset_stub_g": round(self.tare_offset_g, 6),
            "stub_constants": {
                "stable_window_s": self.stable_window_s,
                "pan_load_after_s": round(self.pan_load_after_steps * self.dt, 6),
                "empty_cup_mass_g": self.empty_cup_mass_g,
                "pour_rate_g_s": self.pour_rate_g_s,
                "cap_mass_g": self.cap_mass_g,
                "closed_gripper_width_m": self.closed_gripper_width_m,
            },
        }


# ----------------------------------------------------------------------------------
# Observation construction
# ----------------------------------------------------------------------------------
def _wave1_budget(raw_budget, tracker, dt):
    budget = dict(raw_budget or {})
    budget.update(
        {
            "physics_steps": tracker.physics_steps,
            "remaining_physics_steps": max(0, tracker.max_physics_steps - tracker.physics_steps),
            "calls": tracker.calls_used(),
            "remaining_calls": max(0, tracker.max_api_calls - tracker.calls_used()),
            "max_physics_steps": tracker.max_physics_steps,
            "max_calls": tracker.max_api_calls,
            "physics_dt_s": dt,
            "inference_physics": "paused",
            "finished": False,
        }
    )
    return budget


def build_raw_observation(case, *, sim_time, plant, tracker, balance):
    raw = copy.deepcopy(case.raw_observation)
    raw["simulation_time_s"] = sim_time
    raw["proprioception"] = plant.snapshot()
    if case.wave == "wave1":
        raw["budget"] = _wave1_budget(raw.get("budget"), tracker, tracker.dt)
    else:
        raw.pop("budget", None)
        raw["evaluation"] = {
            "finished": False,
            "task_id": case.task_id,
            "simulation_time_s": sim_time,
        }
        if balance is not None:
            if balance.last_receipt is not None:
                raw["last_instrument_result"] = copy.deepcopy(balance.last_receipt)
            else:
                raw.pop("last_instrument_result", None)
    return raw


# ----------------------------------------------------------------------------------
# Action classification (before the official adapter validates it)
# ----------------------------------------------------------------------------------
def classify_raw_action(action):
    """Return (kind, detail) where kind in finish/step/instrument/invalid."""
    if not isinstance(action, dict):
        return "invalid", f"action must be a dict, got {type(action).__name__}"
    keys = set(action)
    if keys == {"finish"}:
        if action["finish"] is True:
            return "finish", "exact {'finish': True}"
        return "invalid", "finish action must be exactly {'finish': True}"
    if "instrument" in keys:
        if keys != {"instrument"}:
            return "invalid", f"instrument action must not mix other fields, got {sorted(keys)}"
        return "instrument", "instrument-only action"
    if keys - {"arms", "steps"}:
        return "invalid", f"unknown action fields: {sorted(keys - {'arms', 'steps'})}"
    return "step", "arms/steps action"


def _action_signature(raw_action):
    try:
        return json.dumps(
            raw_action, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=repr
        )
    except (TypeError, ValueError):
        return repr(raw_action)


# ----------------------------------------------------------------------------------
# Episode result
# ----------------------------------------------------------------------------------
@dataclass
class EpisodeResult:
    case_id: str
    wave: str
    robot: str
    task_id: str
    synthetic: bool
    mode: str
    cap_reason: str = "unknown"
    finished: bool = False
    violations: list = field(default_factory=list)
    observation_notes: list = field(default_factory=list)
    action_digest: str | None = None
    action_log: list = field(default_factory=list)  # only when keep_action_log
    last_actions: list = field(default_factory=list)
    action_counts: dict = field(default_factory=dict)
    step_values: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    budget: dict = field(default_factory=dict)
    balance: dict | None = None
    instrument_events: list = field(default_factory=list)
    sim_time_start: float = 0.0
    sim_time_end: float = 0.0
    wall_seconds: float = 0.0
    policy_cpu_seconds: float = 0.0
    reset_wall_seconds: float = 0.0
    reset_cpu_seconds: float = 0.0
    exception: str | None = None
    policy_source_loaded: str | None = None

    def violation_codes(self):
        return [violation["code"] for violation in self.violations]

    def to_dict(self, *, include_action_log=False):
        data = {
            "case_id": self.case_id,
            "wave": self.wave,
            "robot": self.robot,
            "task_id": self.task_id,
            "synthetic": self.synthetic,
            "mode": self.mode,
            "cap_reason": self.cap_reason,
            "finished": self.finished,
            "violations": copy.deepcopy(self.violations),
            "violation_codes": self.violation_codes(),
            "observation_notes": list(self.observation_notes),
            "action_digest": self.action_digest,
            "action_counts": copy.deepcopy(self.action_counts),
            "step_values": list(self.step_values),
            "stats": copy.deepcopy(self.stats),
            "budget": copy.deepcopy(self.budget),
            "balance_stub": copy.deepcopy(self.balance),
            "instrument_events": [event.to_dict() for event in self.instrument_events]
            if self.instrument_events and isinstance(self.instrument_events[0], InstrumentEvent)
            else copy.deepcopy(self.instrument_events),
            "sim_time_start_s": round(self.sim_time_start, 6),
            "sim_time_end_s": round(self.sim_time_end, 6),
            "wall_seconds": round(self.wall_seconds, 6),
            "policy_cpu_seconds": round(self.policy_cpu_seconds, 6),
            "reset_wall_seconds": round(self.reset_wall_seconds, 6),
            "reset_cpu_seconds": round(self.reset_cpu_seconds, 6),
            "exception": self.exception,
            "last_actions": copy.deepcopy(self.last_actions),
            "policy_source_loaded": self.policy_source_loaded,
        }
        if include_action_log:
            data["action_log"] = copy.deepcopy(self.action_log)
        return data


# ----------------------------------------------------------------------------------
# Episode runner
# ----------------------------------------------------------------------------------
def run_episode(
    case,
    *,
    package_root,
    rules,
    policy_dir=None,
    policy_source="policy.py",
    policy_factory=None,
    policy_module_patch=None,
    mode="full",
    max_iterations=None,
    wall_clock_limit_s=None,
    balance_mode="nominal",
    gripper_mock=None,
    keep_action_log=False,
    sim_time_override=None,
):
    """Run one offline episode of the policy on a fixture case.

    ``policy_factory`` overrides file loading (used for the driver self-check
    stubs). ``mode='full'`` requires the episode to end with a legal finish;
    ``mode='smoke'`` allows hitting the iteration cap and is used for the
    protocol-synthetic cases so the suite stays bounded.
    """
    adapter_cls, contract_error = ensure_sdk_importable(package_root)
    limits = case_budget_limits(rules, case)
    dt = limits["dt"]
    if max_iterations is None:
        max_iterations = int(limits["max_api_calls"]) + 10
    if wall_clock_limit_s is None:
        wall_clock_limit_s = 300.0

    result = EpisodeResult(
        case_id=case.case_id,
        wave=case.wave,
        robot=case.robot,
        task_id=case.task_id,
        synthetic=case.synthetic,
        mode=mode,
    )
    result.observation_notes.append("offline protocol harness: no images, no object/contact physics")
    result.observation_notes.append(
        "kinematic mock (NOT physics simulation): measured joints/gripper echo the last command,"
        " measured TCP pose recomputed by FK from the public robot_kinematics contract"
    )

    episode_start = time.perf_counter()
    episode_start_cpu = time.process_time()

    def add_violation(code, detail, action_index=None, sim_time=None):
        result.violations.append(
            {
                "code": code,
                "detail": detail,
                "action_index": action_index,
                "sim_time_s": None if sim_time is None else round(sim_time, 6),
            }
        )

    # -- policy construction ------------------------------------------------------
    try:
        factory = policy_factory or make_file_policy_factory(
            policy_dir, policy_source, module_patch=policy_module_patch
        )
        result.policy_source_loaded = (
            str((Path(policy_dir) / policy_source).resolve()) if policy_factory is None else "inline-factory"
        )
        policy = factory()
    except Exception as exc:  # noqa: BLE001 - reported as a test result, not raised
        add_violation("policy_load_exception", f"{type(exc).__name__}: {exc}")
        result.exception = traceback.format_exc(limit=5)
        result.cap_reason = "policy_load_exception"
        result.wall_seconds = time.perf_counter() - episode_start
        result.policy_cpu_seconds = time.process_time() - episode_start_cpu
        return result

    # -- canonical instruction + adapter -----------------------------------------
    try:
        adapter = case.make_adapter()
        instruction = adapter.instruction()
        canonical_observation0 = adapter.observation(case.raw_observation)
    except Exception as exc:  # noqa: BLE001
        add_violation("invalid_action", f"fixture/adaptor failure: {type(exc).__name__}: {exc}")
        result.cap_reason = "harness_error"
        return result

    if getattr(policy, "observation_images", False):
        result.observation_notes.append(
            "policy declares observation_images=True; offline harness provides no images "
            "(canonical observation keeps only proprioception/time)"
        )

    tracker = BudgetTracker(case.wave, limits)
    plant = PlantState(adapter, instruction, case.raw_observation)
    balance = FakeBalance(mode=balance_mode, dt=dt) if (case.wave == "wave2" and case.task_id == "C07") else None
    if balance is not None:
        result.observation_notes.append(
            "C07 balance receipts are scripted protocol stubs (FakeBalance), not real measurements"
        )

    sim_time = float(sim_time_override if sim_time_override is not None
                     else case.raw_observation["simulation_time_s"])
    result.sim_time_start = sim_time

    # -- reset --------------------------------------------------------------------
    reset_cpu0 = time.process_time()
    reset_wall0 = time.perf_counter()
    try:
        policy.reset(copy.deepcopy(instruction))
    except Exception as exc:  # noqa: BLE001
        add_violation("reset_exception", f"{type(exc).__name__}: {exc}")
        result.exception = traceback.format_exc(limit=5)
        result.cap_reason = "reset_exception"
        result.reset_cpu_seconds = time.process_time() - reset_cpu0
        result.reset_wall_seconds = time.perf_counter() - reset_wall0
        result.wall_seconds = time.perf_counter() - episode_start
        result.policy_cpu_seconds = time.process_time() - episode_start_cpu
        return result
    result.reset_cpu_seconds = time.process_time() - reset_cpu0
    result.reset_wall_seconds = time.perf_counter() - reset_wall0

    # Keep the canonical first observation available for policies that expect the
    # reset observation to be replayable; our loop synthesizes fresh observations.
    del canonical_observation0

    action_records = []  # normalized raw actions, for the determinism digest
    action_counts = {"step": 0, "instrument_read": 0, "instrument_tare": 0, "finish": 0, "invalid": 0}
    step_values = []
    last_actions = []
    instrument_events = []
    hold_steps_since_motion = 0
    last_motion_sim_time = None

    def remember(kind, raw_action, canonical_action=None, receipt=None):
        entry = {
            "kind": kind,
            "raw_action": copy.deepcopy(raw_action),
            "canonical_action": copy.deepcopy(canonical_action),
            "receipt": copy.deepcopy(receipt),
            "sim_time_s": round(sim_time, 6),
        }
        last_actions.append(entry)
        if len(last_actions) > 12:
            last_actions.pop(0)
        if keep_action_log:
            result.action_log.append(entry)

    def policy_budget_guard(index):
        codes = tracker.exceeded()
        if "budget_steps_exceeded" in codes:
            add_violation(
                "budget_steps_exceeded",
                f"physics steps used {tracker.physics_steps} > {tracker.max_physics_steps}",
                index,
                sim_time,
            )
        if "budget_calls_exceeded" in codes:
            add_violation(
                "budget_calls_exceeded",
                f"wave1 API calls used {tracker.calls_used()} > {tracker.max_api_calls}",
                index,
                sim_time,
            )
        if "budget_requests_exceeded" in codes:
            add_violation(
                "budget_requests_exceeded",
                f"unique mutating requests {tracker.unique_requests} > {tracker.max_api_calls}",
                index,
                sim_time,
            )
        return bool(codes)

    cap_reason = "max_iterations"
    index = 0
    while True:
        index += 1
        if index > max_iterations:
            add_violation(
                "loop_guard",
                f"episode exceeded max_iterations={max_iterations} without finishing",
                index,
                sim_time,
            )
            cap_reason = "loop_guard"
            break
        if (time.perf_counter() - episode_start) > wall_clock_limit_s:
            add_violation(
                "wall_clock_guard",
                f"episode exceeded offline wall-clock guard {wall_clock_limit_s}s",
                index,
                sim_time,
            )
            cap_reason = "wall_clock_guard"
            break

        # -- observation ----------------------------------------------------------
        raw_obs = build_raw_observation(
            case, sim_time=sim_time, plant=plant, tracker=tracker, balance=balance
        )
        try:
            observation = adapter.observation(raw_obs)
        except contract_error as exc:
            add_violation("invalid_action", f"driver observation invalid: {exc}", index, sim_time)
            cap_reason = "harness_error"
            break
        tracker.observe()

        # -- act ------------------------------------------------------------------
        act_cpu0 = time.process_time()
        try:
            raw_action = policy.act(observation)
        except Exception as exc:  # noqa: BLE001
            add_violation("act_exception", f"{type(exc).__name__}: {exc}", index, sim_time)
            result.exception = traceback.format_exc(limit=8)
            cap_reason = "act_exception"
            break
        finally:
            result.policy_cpu_seconds += time.process_time() - act_cpu0

        action_records.append({"kind": "act", "action": _action_signature(raw_action)})
        kind, detail = classify_raw_action(raw_action)

        if kind == "invalid":
            action_counts["invalid"] += 1
            add_violation("invalid_action", detail, index, sim_time)
            remember("invalid", raw_action)
            cap_reason = "invalid_action"
            break

        if kind == "finish":
            action_counts["finish"] += 1
            tracker.record_finish(raw_action)
            canonical_action = {"finish": True}
            result.finished = True
            # Native backend finish behaviour: wave1 holds +720 physics steps,
            # wave2 adds 0 (exactly what the Adapter exposes as finish_steps).
            finish_steps = int(getattr(adapter, "finish_steps", 0))
            sim_time += finish_steps * dt
            remember("finish", raw_action, canonical_action)
            result.stats["finish_extra_physics_steps"] = finish_steps
            result.stats["finish_sim_time_s"] = round(sim_time, 6)
            if policy_budget_guard(index):
                cap_reason = "budget_exceeded"
            else:
                cap_reason = "finish"
            break

        if kind == "instrument":
            action_counts["invalid"] += 0  # counted below by method
            try:
                canonical_action = adapter.action(raw_action)
            except contract_error as exc:
                action_counts["invalid"] += 1
                add_violation("invalid_action", f"adapter rejected instrument action: {exc}", index, sim_time)
                remember("invalid", raw_action)
                cap_reason = "invalid_action"
                break
            method = canonical_action["instrument"]["method"]
            action_counts[f"instrument_{method}"] += 1
            tracker.record_instrument(raw_action)
            if balance is None:
                add_violation(
                    "instrument_not_allowed",
                    f"instrument action is only allowed on wave2 C07, case={case.task_id}",
                    index,
                    sim_time,
                )
                cap_reason = "invalid_action"
                break
            stable_before = balance.is_stable(sim_time)
            receipt, instrument_violations = balance.handle(method, sim_time)
            for code in instrument_violations:
                add_violation(code, f"balance stub reported {code} during {method}", index, sim_time)
            event = InstrumentEvent(
                index=index,
                method=method,
                sim_time=sim_time,
                stable_before_call=stable_before,
                receipt=copy.deepcopy(receipt),
                violations=list(instrument_violations),
                raw_action=copy.deepcopy(raw_action),
            )
            instrument_events.append(event)
            remember("instrument", raw_action, canonical_action, receipt)
            if policy_budget_guard(index):
                cap_reason = "budget_exceeded"
                break
            continue

        # kind == "step"
        try:
            canonical_action = adapter.action(raw_action)
        except contract_error as exc:
            action_counts["invalid"] += 1
            add_violation("invalid_action", f"adapter rejected action: {exc}", index, sim_time)
            remember("invalid", raw_action)
            cap_reason = "invalid_action"
            break
        steps = int(canonical_action["steps"])
        step_values.append(steps)
        action_counts["step"] += 1
        tracker.record_step(raw_action, steps)
        sim_time_before = sim_time
        sim_time += steps * dt
        motion = plant.apply(canonical_action, gripper_mock=gripper_mock)
        if motion["moved"]:
            last_motion_sim_time = sim_time
            hold_steps_since_motion = 0
        else:
            hold_steps_since_motion += steps
        if balance is not None:
            balance.notify_step(canonical_action, sim_time, motion["moved"])
        remember("step", raw_action, canonical_action)
        if last_actions:
            last_actions[-1]["moved"] = bool(motion["moved"])
            last_actions[-1]["steps"] = steps
        if policy_budget_guard(index):
            cap_reason = "budget_exceeded"
            break

    # -- wrap up ------------------------------------------------------------------
    if mode == "full" and not result.finished and not result.violations:
        add_violation("no_finish", f"episode ended ({cap_reason}) without a legal finish", index, sim_time)
    if result.violations and cap_reason in ("finish",):
        cap_reason = "finish_with_violations"

    result.cap_reason = cap_reason
    result.sim_time_end = sim_time
    result.action_digest = hashlib.sha256(
        json.dumps(action_records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    result.action_counts = action_counts
    result.step_values = step_values
    result.last_actions = last_actions
    result.instrument_events = instrument_events
    result.budget = tracker.snapshot()
    if balance is not None:
        result.balance = balance.summary()
    total_steps = sum(step_values)
    result.stats.update(
        {
            "act_calls": tracker.observation_calls,
            "step_actions": action_counts["step"],
            "instrument_actions": tracker.instrument_calls,
            "finish_actions": action_counts["finish"],
            "steps_total_from_actions": total_steps,
            "physics_steps_tracked": tracker.physics_steps,
            "hold_steps_since_last_motion": hold_steps_since_motion,
            "terminal_hold_steps": hold_steps_since_motion,
            "terminal_hold_seconds": round(hold_steps_since_motion * dt, 6),
            "last_motion_sim_time_s": None if last_motion_sim_time is None else round(last_motion_sim_time, 6),
            "min_steps": min(step_values) if step_values else None,
            "max_steps": max(step_values) if step_values else None,
            "distinct_steps_values": sorted(set(step_values)),
            "sim_time_end_s": round(sim_time, 6),
        }
    )
    result.policy_cpu_seconds += time.process_time() - episode_start_cpu - result.reset_cpu_seconds
    result.wall_seconds = time.perf_counter() - episode_start
    if result.policy_cpu_seconds > limits.get("policy_cpu_seconds", 120):
        add_violation(
            "policy_cpu_budget_exceeded",
            f"policy CPU {result.policy_cpu_seconds:.3f}s > {limits['policy_cpu_seconds']}s",
            index,
            sim_time,
        )
    return result
