"""lab-policy-v2 entry point: one frozen policy for the nine public tasks.

Protocol surface (docs/SDK.md):
  * ``Policy()`` takes no arguments;
  * ``reset(instruction)`` runs once per episode;
  * ``act(observation)`` returns exactly one action:
        {"arms": {<arm>: {"positions": [...], "gripper_width_m": m}}, "steps": 1..120}
        {"instrument": {"device": "competition_balance", "method": "read"|"tare"}}   # C07 only
        {"finish": True}
  * joint counts/order, gripper range, physics step and finish contract are read
    from the instruction (Franka: 7 joints on ``arm``; dual PiPER: 6 joints on
    ``left``/``right``); nothing about another robot/wave is hard-coded.

Public-observation-only rule: the policy consumes ``proprioception``, the
supplied RGB camera payloads and the declared instrument receipts.  It never
reads object truth poses, contact truth or judge state.

Perception hook (module level so a development harness can substitute synthetic
detections while testing the state machine; production uses the real RGB
helpers in ``vision.py``).  ``perceive(observation, kind, camera=None)``
returns:
  * "frames": {"green": blob, "blue": blob} (blob = {"cx","cy","image_w","image_h",...})
  * "caps":  list[blob]
  * "bright" / "dark" / "green" / "blue": single blob or None
  * "cup_receiving" / "pan" / "cup_source": single blob or None
  * "liquid": {"fill_fraction": 0..1, ...} or None
``None`` always means "not confidently detected" and skills stop safely.
"""

import math

import kinematics
import skills
import vision


def perceive(observation, kind, camera=None):
    """Default RGB perception hook (module-level so it can be substituted)."""
    try:
        if kind == "frames":
            return vision.detect_frames(observation, camera or "overhead")
        if kind == "caps":
            return vision.detect_white_caps(observation, camera or "overhead")
        if kind == "liquid":
            return vision.estimate_liquid_line(observation, camera or "overhead")
        if kind in ("bright", "dark"):
            return vision.detect_bright_or_dark(observation, kind, camera)
        if kind == "white":
            return vision.detect_bright_or_dark(observation, "white", camera)
        if kind in ("green", "blue"):
            frames = vision.detect_frames(observation, camera or "overhead") or {}
            return frames.get(kind)
        if kind in ("cup_receiving", "pan", "cup_source"):
            blobs = vision.detect_bright_blobs(observation, camera)
            if not blobs:
                return None
            if kind == "pan":
                wide = [b for b in blobs if b.get("width_px", 0) >= b.get("height_px", 0)]
                return (wide or blobs)[0]
            if kind == "cup_source":
                return blobs[1] if len(blobs) > 1 else blobs[0]
            return blobs[0]
        return None
    except Exception:
        return None


class Policy:
    """One deterministic controller for the nine-task track."""

    observation_images = True

    #: published second-wave per-trial caps (docs/TASKS.md); each C task runs 1200 s
    WAVE2_SIMULATION_SECONDS = 1200.0
    WAVE2_MAX_CALLS = 10000

    def __init__(self):
        self.arms = {}
        self.task = None
        self.wave = None
        self.robot = None
        self.dt = None
        self.hz = None
        self.max_steps_per_action = 120
        self.finish_extra_steps = 0
        self.ctx = None
        self.skill = None
        self.finished = False
        self.fault = None
        self.action_count = 0
        self.steps_used = 0
        self.calls_used = 0
        self.max_physics_steps = None
        self.max_calls = None
        self._finish_hold_left = 0
        self._finish_started = False

    # ------------------------------------------------------------------
    # protocol
    # ------------------------------------------------------------------
    def reset(self, instruction):
        self.arms = {}
        self.finished = False
        self.fault = None
        self.action_count = 0
        self.steps_used = 0
        self.calls_used = 0
        self._finish_hold_left = 0
        self._finish_started = False
        self.instruction = instruction if isinstance(instruction, dict) else {}
        if self.instruction.get("schema") != "lab-instruction/v2":
            self.fault = "unexpected instruction schema"
            return
        self.task = self.instruction.get("task_id")
        self.wave = self.instruction.get("backend_wave")
        self.robot = self.instruction.get("robot_profile")
        physics = self.instruction.get("physics") or {}
        self.dt = float(physics.get("step_seconds"))
        self.hz = float(physics.get("frequency_hz"))
        self.max_steps_per_action = int(physics.get("maximum_steps_per_action") or 120)
        finish = self.instruction.get("finish") or {}
        self.finish_extra_steps = int(finish.get("extra_physics_steps") or 0)
        arms = self.instruction.get("arms") or {}
        kinematics_map = self.instruction.get("robot_kinematics") or {}
        for name, spec in arms.items():
            kin = kinematics_map.get(name)
            if not isinstance(spec, dict) or not isinstance(kin, dict):
                self.fault = "missing public arm kinematics"
                continue
            names = spec.get("joint_names")
            width = spec.get("gripper_width_m")
            if not isinstance(names, list) or not isinstance(width, (list, tuple)) or len(width) != 2:
                self.fault = "missing public arm limits"
                continue
            try:
                self.arms[str(name)] = kinematics.ArmModel(
                    name, kin, [str(n) for n in names], float(width[1]))
            except (TypeError, ValueError, KeyError):
                self.fault = "unusable public arm kinematics"
        if not self.arms:
            self.fault = "no usable arms"
        # budget guard rails (public contracts)
        budget = self.instruction.get("budget")
        if isinstance(budget, dict) and budget.get("max_physics_steps") is not None:
            self.max_physics_steps = int(budget["max_physics_steps"])
            self.max_calls = int(budget.get("max_calls") or 0) or None
        elif self.wave == "wave2":
            self.max_physics_steps = int(self.WAVE2_SIMULATION_SECONDS * self.hz)
            self.max_calls = self.WAVE2_MAX_CALLS
        self.ctx = skills.Context(self) if self.arms else None
        self.skill = skills.make_skill(self.ctx) if (self.fault is None and self.ctx is not None) else None

    def act(self, observation):
        # terminal guard: once finished, keep the terminal action stable
        if self.finished:
            return {"finish": True}
        if self.fault is not None or self.ctx is None:
            return self._finish_tick()
        try:
            self.ctx.update(observation)
        except Exception:
            self.fault = "observation not usable"
            return self._finish_tick()
        # keep the perception hook replaceable by the development harness
        self.ctx.perceive_impl = perceive

        if self.action_count > 6000:
            return self._finish_tick()
        if not self._budget_ok():
            return self._finish_tick()

        if self.skill is None:
            return self._finish_tick()
        try:
            action = next(self.skill)
        except StopIteration:
            self.skill = None
            return self._finish_tick()
        except Exception:
            # a skill bug must never emit an illegal action; stop safely
            self.fault = "skill exception"
            return self._finish_tick()
        self.action_count += 1
        return self._validate_action(action)

    # ------------------------------------------------------------------
    # action validation / accounting
    # ------------------------------------------------------------------
    def _validate_action(self, action):
        if not isinstance(action, dict) or not action:
            return self._finish_tick()
        if set(action) == {"finish"} and action["finish"] is True:
            return self._finish_tick()
        if set(action) == {"instrument"}:
            command = action["instrument"]
            allowed = (self.wave == "wave2" and self.task == "C07" and isinstance(command, dict)
                       and set(command) == {"device", "method"}
                       and command["device"] == "competition_balance"
                       and command["method"] in ("read", "tare"))
            if not allowed:
                return self._finish_tick()
            self.calls_used += 1
            return action
        if set(action) - {"arms", "steps"}:
            return self._finish_tick()
        steps = action.get("steps", 1)
        if type(steps) is not int or not 1 <= steps <= self.max_steps_per_action:
            return self._finish_tick()
        arms = action.get("arms") or {}
        if not isinstance(arms, dict) or not arms:
            return self._finish_tick()
        checked = {}
        for name, command in arms.items():
            model = self.arms.get(name)
            if model is None or not isinstance(command, dict):
                return self._finish_tick()
            if set(command) - {"positions", "gripper_width_m"}:
                return self._finish_tick()
            positions = command.get("positions")
            if not isinstance(positions, (list, tuple)) or len(positions) != model.n:
                return self._finish_tick()
            clean = []
            for value in positions:
                if type(value) not in (int, float) or not math.isfinite(float(value)):
                    return self._finish_tick()
                clean.append(float(value))
            width = command.get("gripper_width_m")
            if width is None:
                width = 0.0
            if type(width) not in (int, float) or not math.isfinite(float(width)):
                return self._finish_tick()
            width = max(0.0, min(float(width), model.gripper_max))
            checked[name] = {"positions": clean, "gripper_width_m": width}
        self.steps_used += steps
        self.calls_used += 1
        return {"arms": checked, "steps": steps}

    def _budget_ok(self):
        reserve_steps = 800 if self.wave == "wave1" else 600
        reserve_calls = 8
        if self.max_physics_steps is not None and self.steps_used > self.max_physics_steps - reserve_steps:
            return False
        if self.max_calls is not None and self.calls_used > self.max_calls - reserve_calls:
            return False
        return True

    # ------------------------------------------------------------------
    # finish contract
    # ------------------------------------------------------------------
    def _finish_tick(self):
        """Honour the two published finish contracts.

        wave1: ``finish`` makes the backend hold the current targets for 720
        real steps and then ends the episode - the policy must NOT add steps.
        wave2: ``finish`` adds no physics, so the policy itself has to spend
        real settling steps (well over the 1 s terminal window) first.  Every
        remaining settling step is emitted as a hold action *before* the
        terminal action; the final chunk must not be swallowed by the finish.
        """
        if self.wave == "wave1" or self.finish_extra_steps != 0:
            self.finished = True
            return {"finish": True}
        if self._finish_hold_left <= 0 and not self._finish_started:
            total = int(math.ceil(1.25 / float(self.dt)))
            self._finish_hold_left = total
            self._finish_started = True
        if self._finish_hold_left <= 0:
            self.finished = True
            return {"finish": True}
        steps = min(self.max_steps_per_action, max(1, self._finish_hold_left))
        self._finish_hold_left -= steps
        arms = {}
        for name, model in self.arms.items():
            q = self.ctx.joint_vector(name) if self.ctx is not None else None
            if q is None:
                q = [0.0] * model.n
            width = self.ctx.gripper_width(name, 0.0) if self.ctx is not None else 0.0
            arms[name] = {"positions": q, "gripper_width_m": float(width or 0.0)}
        self.steps_used += steps
        self.calls_used += 1
        return {"arms": arms, "steps": steps}
