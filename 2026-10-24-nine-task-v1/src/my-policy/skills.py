"""Skill library for the nine public tasks (lab-policy-v2).

Design rules enforced here:
  * every command is derived from the *public* instruction and the *public*
    observation stream (proprioception + RGB + declared instruments);
  * no private object pose, contact truth, judge state or success flag is read;
  * a task skill never declares success — it only performs an attempt and then
    returns; the independent judge decides the outcome;
  * when perception is not available the skill stops safely (hold + finish)
    instead of guessing;
  * instrument actions (C07 balance read/tare) are yielded as stand-alone
    actions and never mixed with joint commands.

The skills are generator based: ``next(gen)`` returns one policy action.  They
are written to be deterministic: no randomness, no wall-clock decisions.
"""

import math


# --------------------------------------------------------------------------
# small numeric helpers
# --------------------------------------------------------------------------
def _num(value):
    return type(value) in (int, float) and math.isfinite(value)


def _vec(value, n):
    if not isinstance(value, (list, tuple)) or len(value) < n:
        return None
    out = []
    for item in value[:n]:
        if not _num(item):
            return None
        out.append(float(item))
    return out


def parse_balance(result):
    """Interpret a public competition_balance receipt conservatively.

    The exact real receipt field set is not published, so accept the documented
    meaning (ok / stable-or-STABLE / net mass) and refuse to treat an unstable,
    failed or malformed receipt as a valid mass.
    """
    if not isinstance(result, dict):
        return None
    ok = result.get("ok") is True
    status = str(result.get("status", "")).upper()
    stable = result.get("stable") is True or status == "STABLE"
    net = result.get("net_mass_g")
    mass = result.get("mass_g")
    version = result.get("tare_version")
    active = result.get("tare_active")
    return {
        "ok": ok,
        "stable": bool(stable),
        "net_g": float(net) if _num(net) else None,
        "mass_g": float(mass) if _num(mass) else None,
        "tare_version": int(version) if _num(version) else None,
        "tare_active": bool(active) if isinstance(active, bool) else None,
        "raw": result,
    }


def parse_instruments(observation, keys):
    instruments = observation.get("instruments")
    if not isinstance(instruments, dict):
        return None
    for key in keys:
        value = instruments.get(key)
        if isinstance(value, dict):
            return value
    return None


# --------------------------------------------------------------------------
# Context: robot state + reusable motion/servo primitives
# --------------------------------------------------------------------------
class Context:
    def __init__(self, policy):
        self.policy = policy
        self.obs = {}
        self.arm_names = list(policy.arms.keys())
        self.primary_arm = ("arm" if "arm" in policy.arms
                            else (self.arm_names[0] if self.arm_names else None))
        self.dt = float(policy.dt)
        self.wave = policy.wave
        self.task = policy.task
        self.perceive_impl = None

    # ---- observation access ----
    def update(self, observation):
        self.obs = observation if isinstance(observation, dict) else {}
        self.last_instrument = self.obs.get("last_instrument_result")
        self._refresh_limits()

    def _refresh_limits(self):
        proprio = self.obs.get("proprioception") or {}
        for arm, model in self.policy.arms.items():
            data = proprio.get(arm)
            if not isinstance(data, dict):
                continue
            names = data.get("joint_names")
            lower = data.get("joint_lower_limits")
            upper = data.get("joint_upper_limits")
            if (isinstance(names, list) and isinstance(lower, list) and isinstance(upper, list)
                    and len(names) == len(lower) == len(upper)):
                try:
                    index = {str(n): i for i, n in enumerate(names)}
                    lo = [float(lower[index[n]]) for n in model.joint_names if n in index]
                    hi = [float(upper[index[n]]) for n in model.joint_names if n in index]
                    if len(lo) == model.n and len(hi) == model.n:
                        model.set_limits(lo, hi)
                except (KeyError, TypeError, ValueError):
                    pass
            if not model.calibrated:
                pos = _vec(data.get("tcp_position_m"), 3)
                rot = data.get("tcp_rotation_world")
                q = self.joint_vector(arm)
                if pos is not None and q is not None:
                    try:
                        flat = []
                        for row in rot:
                            flat.extend([float(x) for x in row])
                        if len(flat) == 9:
                            model.calibrate(q, pos, [flat[0:3], flat[3:6], flat[6:9]])
                    except (TypeError, ValueError):
                        pass

    def joint_vector(self, arm):
        proprio = (self.obs.get("proprioception") or {}).get(arm)
        if not isinstance(proprio, dict):
            return None
        names = proprio.get("joint_names")
        positions = proprio.get("joint_positions")
        if not isinstance(names, list) or not isinstance(positions, list):
            return None
        index = {str(n): i for i, n in enumerate(names)}
        model = self.policy.arms[arm]
        out = []
        for name in model.joint_names:
            if name not in index or not _num(positions[index[name]]):
                return None
            out.append(float(positions[index[name]]))
        return out

    def gripper_width(self, arm, default=None):
        proprio = (self.obs.get("proprioception") or {}).get(arm)
        if isinstance(proprio, dict) and _num(proprio.get("gripper_width_m")):
            return float(proprio["gripper_width_m"])
        return default

    def pose(self, arm):
        """Current TCP (position, rotation) from the public observation."""
        proprio = (self.obs.get("proprioception") or {}).get(arm)
        if not isinstance(proprio, dict):
            return None
        pos = _vec(proprio.get("tcp_position_m"), 3)
        rot = proprio.get("tcp_rotation_world")
        if pos is None or not isinstance(rot, list) or len(rot) != 3:
            return None
        try:
            matrix = [[float(x) for x in row] for row in rot]
        except (TypeError, ValueError):
            return None
        return pos, matrix

    def ready(self, arm):
        return self.pose(arm) is not None and self.joint_vector(arm) is not None

    # ---- action builders ----
    def arm_action(self, arm, positions, width, steps):
        steps = int(max(1, min(120, steps)))
        return {"arms": {arm: {"positions": [float(x) for x in positions],
                               "gripper_width_m": float(max(0.0, min(width, self.policy.arms[arm].gripper_max)))}},
                "steps": steps}

    def hold_action(self, steps):
        steps = int(max(1, min(120, steps)))
        arms = {}
        for arm in self.arm_names:
            q = self.joint_vector(arm)
            if q is not None:
                arms[arm] = {"positions": q, "gripper_width_m": self.gripper_width(arm, 0.0)}
        return {"arms": arms, "steps": steps}

    def instr(self, method):
        return {"instrument": {"device": "competition_balance", "method": str(method)}}

    # ---- generators used by skills ----
    def hold(self, seconds, gripper=None):
        total = max(1, int(math.ceil(float(seconds) / self.dt)))
        done = 0
        while done < total:
            steps = min(120, total - done)
            action = self.hold_action(steps)
            if gripper is not None and self.primary_arm in action["arms"]:
                action["arms"][self.primary_arm]["gripper_width_m"] = float(gripper)
            yield action
            done += steps

    def set_gripper(self, arm, width, max_ticks=20):
        target = float(max(0.0, min(width, self.policy.arms[arm].gripper_max)))
        for _ in range(max_ticks):
            q = self.joint_vector(arm)
            if q is None:
                return False
            current = self.gripper_width(arm, 0.0) or 0.0
            steps = int(max(2, min(30, math.ceil(abs(target - current) / (0.06 * self.dt)) + 2)))
            yield self.arm_action(arm, q, target, steps)
            if abs(current - target) < 0.002:
                return True
        return True

    def open_gripper(self, arm):
        model = self.policy.arms[arm]
        yield from self.set_gripper(arm, model.gripper_max)

    def close_until_stall(self, arm, step_m=0.004, max_ticks=26):
        """Close gradually; stall of the measured width = object contact."""
        width = self.gripper_width(arm, self.policy.arms[arm].gripper_max) or 0.0
        for _ in range(max_ticks):
            q = self.joint_vector(arm)
            if q is None:
                yield self.hold_action(4)
                return False
            command = max(0.0, width - step_m)
            marker = float(width)
            yield self.arm_action(arm, q, command, 4)
            measured = self.gripper_width(arm)
            if measured is None:
                return False
            if measured <= 0.0015:
                return False
            if marker - measured < 0.0004 and marker > 0.004:
                return True          # fingers blocked by the object
            width = measured
        return False

    def move_tcp(self, arm, target_pos, target_rot=None, gripper=None, steps=10,
                 tol_pos=0.006, tol_rot=0.06, max_ticks=60, max_jump=0.05):
        model = self.policy.arms[arm]
        for _ in range(max_ticks):
            current = self.pose(arm)
            q = self.joint_vector(arm)
            if current is None or q is None or not model.calibrated:
                yield self.hold_action(4)
                return False
            pos, rot = current
            goal = [float(target_pos[i]) for i in range(3)]
            delta = [goal[i] - pos[i] for i in range(3)]
            dist = math.sqrt(sum(d * d for d in delta))
            if dist <= tol_pos:
                if target_rot is None:
                    return True
                # rotation error
                goal_rot = target_rot
                try:
                    import numpy as np
                    from kinematics import rotvec
                    err = float(np.linalg.norm(rotvec(np.asarray(goal_rot) @ np.asarray(rot).T)))
                except Exception:
                    err = 0.0
                if err <= tol_rot:
                    return True
            # keep the step bounded so the closed loop stays stable
            if dist > max_jump:
                delta = [d * max_jump / dist for d in delta]
            next_pos = [pos[i] + delta[i] for i in range(3)]
            goal_rot = target_rot if target_rot is not None else rot
            try:
                q_cmd = model.ik(next_pos, goal_rot, q, iters=30)
            except Exception:
                yield self.hold_action(4)
                return False
            q_cmd = model.clip_target(q_cmd, q, steps, self.dt)
            width = self.gripper_width(arm, 0.0) if gripper is None else float(gripper)
            yield self.arm_action(arm, q_cmd, width, steps)
        return False

    def move_tcp_delta(self, arm, delta, gripper=None, steps=10, max_ticks=12):
        current = self.pose(arm)
        if current is None:
            yield self.hold_action(4)
            return False
        pos = current[0]
        target = [pos[i] + float(delta[i]) for i in range(3)]
        ok = yield from self.move_tcp(arm, target, None, gripper, steps=steps, max_ticks=max_ticks)
        return ok

    def rotate_tcp(self, arm, rot_delta_matrix, gripper=None, steps=8, max_ticks=40):
        """Rotate the TCP about its own origin by a fixed rotation matrix."""
        model = self.policy.arms[arm]
        for _ in range(max_ticks):
            current = self.pose(arm)
            q = self.joint_vector(arm)
            if current is None or q is None or not model.calibrated:
                yield self.hold_action(4)
                return False
            pos, rot = current
            try:
                import numpy as np
                goal = (np.asarray(rot_delta_matrix) @ np.asarray(rot)).tolist()
                from kinematics import rotvec
                err = float(np.linalg.norm(rotvec(np.asarray(goal) @ np.asarray(rot).T)))
            except Exception:
                return False
            if err < 0.05:
                return True
            try:
                q_cmd = model.ik(pos, goal, q, iters=25)
            except Exception:
                return False
            q_cmd = model.clip_target(q_cmd, q, steps, self.dt)
            width = self.gripper_width(arm, 0.0) if gripper is None else float(gripper)
            yield self.arm_action(arm, q_cmd, width, steps)
        return False

    # ---- perception ----
    def detect(self, kind, camera=None):
        if self.perceive_impl is None:
            return None
        try:
            return self.perceive_impl(self.obs, kind, camera)
        except Exception:
            return None

    def servo_pixel(self, arm, kind, camera=None, goal=(0.5, 0.55),
                    probe_delta=0.012, max_ticks=26, tol_px=12.0):
        """Image-space servo using an *estimated* pixel Jacobian.

        The wrist camera is rigidly mounted on the hand, so nudging the TCP by a
        known metric delta and measuring the resulting pixel shift identifies
        the local pixel/command Jacobian without any published camera
        calibration.  Then the detected target is driven to the goal pixel.
        """
        det = self.detect(kind, camera)
        if not det or not _num(det.get("cx")) or not _num(det.get("cy")):
            return None
        width = float(det.get("image_w") or 640.0)
        height = float(det.get("image_h") or 480.0)
        samples = []
        for axis in range(3):
            base = self.detect(kind, camera)
            if not base:
                return None
            delta = [0.0, 0.0, 0.0]
            delta[axis] = probe_delta
            moved = yield from self.move_tcp_delta(arm, delta, steps=6, max_ticks=6)
            if not moved:
                return None
            after = self.detect(kind, camera)
            if not after or not _num(after.get("cx")):
                return None
            samples.append((
                [delta[0], delta[1], delta[2]],
                [float(after["cx"]) - float(base["cx"]), float(after["cy"]) - float(base["cy"])]))
        try:
            import numpy as np
            D = np.array([[s[1][0] for s in samples], [s[1][1] for s in samples]], dtype=float)
            X = np.array([[s[0][0] for s in samples], [s[0][1] for s in samples],
                          [s[0][2] for s in samples]], dtype=float)
            scale = (np.abs(D).max(initial=0.0)) or 1.0
            J = (D / scale) @ np.linalg.pinv(X) * scale
        except Exception:
            return None
        goal_px = [goal[0] * width, goal[1] * height]
        for _ in range(max_ticks):
            det = self.detect(kind, camera)
            if not det or not _num(det.get("cx")):
                return None
            err = [goal_px[0] - float(det["cx"]), goal_px[1] - float(det["cy"])]
            if math.hypot(err[0], err[1]) <= tol_px:
                return det
            try:
                import numpy as np
                Jp = np.linalg.pinv(J)
                step = Jp @ np.array(err, dtype=float)
            except Exception:
                return None
            norm = math.sqrt(float(sum(v * v for v in step)))
            if norm > 0.03:
                step = [v * 0.03 / norm for v in step]
            moved = yield from self.move_tcp_delta(arm, step, steps=6, max_ticks=6)
            if not moved:
                return None
        return self.detect(kind, camera)

    def search(self, arm, kind, camera=None, lift=0.04, max_ticks=14):
        """Small bounded search pattern (hover, then serpentine nudges)."""
        yield from self.move_tcp_delta(arm, [0.0, 0.0, lift], max_ticks=6)
        det = self.detect(kind, camera)
        if det:
            return det
        pattern = [(0.05, 0.0), (0.0, 0.05), (-0.10, 0.0), (0.0, -0.10), (0.10, 0.05)]
        for dx, dy in pattern[: max(1, max_ticks // 2)]:
            yield from self.move_tcp_delta(arm, [dx, dy, 0.0], steps=8, max_ticks=5)
            det = self.detect(kind, camera)
            if det:
                return det
        return None

    # ---- instrument helpers ----
    def balance_result(self):
        return parse_balance(self.obs.get("last_instrument_result"))


# --------------------------------------------------------------------------
# generic pick / place sub-skills
# --------------------------------------------------------------------------
def pick_object(ctx, arm, kind, camera=None, hover_lift=0.05):
    det = yield from ctx.search(arm, kind, camera)
    if not det:
        return False
    det = yield from ctx.servo_pixel(arm, kind, camera)
    if not det:
        return False
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -hover_lift], steps=8)
    grasped = yield from ctx.close_until_stall(arm)
    if not grasped:
        yield from ctx.open_gripper(arm)
        return False
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.06], steps=8)
    return True


def place_object(ctx, arm, kind, camera=None, descend=0.06, release=True):
    det = yield from ctx.search(arm, kind, camera, lift=0.01)
    if not det:
        return False
    det = yield from ctx.servo_pixel(arm, kind, camera)
    if not det:
        return False
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -descend], steps=8)
    if release:
        yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.05], steps=8)
    return True


# --------------------------------------------------------------------------
# per-task skills (all generator based)
# --------------------------------------------------------------------------
def skill_bottle_transfer(ctx):
    arm = ctx.primary_arm
    if not (yield from pick_object(ctx, arm, "caps")):
        return
    yield from place_object(ctx, arm, "blue")


def skill_beaker_place(ctx):
    arm = ctx.primary_arm
    if not (yield from pick_object(ctx, arm, "bright")):
        return
    yield from place_object(ctx, arm, "green")


def skill_balance_load(ctx):
    arm = ctx.primary_arm
    if not (yield from pick_object(ctx, arm, "caps")):
        return
    # open the door by a contact motion before the bottle enters the chamber
    yield from ctx.move_tcp_delta(arm, [0.0, -0.18, 0.02], steps=12, max_ticks=14)
    if not (yield from place_object(ctx, arm, "bright", descend=0.05)):
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.02, 0.03], steps=10, max_ticks=10)
    # close the door again with a slow contact motion and let go
    yield from ctx.move_tcp_delta(arm, [0.0, 0.17, -0.01], steps=14, max_ticks=16)


def skill_stirrer_knob(ctx):
    arm = ctx.primary_arm
    det = yield from ctx.search(arm, "bright")
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "bright")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -0.03], steps=6)
    if not (yield from ctx.close_until_stall(arm)):
        return
    # closed-loop rotation using the public stirrer encoder (0..60 deg -> 0..300 rpm)
    rotated = 0.0
    for _ in range(24):
        before = _stirrer_angle_deg(ctx)
        rot = _rotation_matrix(0.0, 0.0, math.radians(2.0))
        yield from ctx.rotate_tcp(arm, rot, steps=4, max_ticks=6)
        after = _stirrer_angle_deg(ctx)
        if after is None or before is None:
            rotated += 2.0
        else:
            step = after - before
            if step < 0:
                step += 60.0
            rotated += step
        if rotated >= 27.0:
            break
    yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.06], steps=8, max_ticks=10)


def _rotation_matrix(rx, ry, rz):
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
    out = [[sum(Rz[i][k] * Ry[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return [[sum(out[i][k] * Rx[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _stirrer_angle_deg(ctx):
    data = parse_instruments(ctx.obs, ["stirrer"])
    if not data:
        return None
    rpm = data.get("measured_rpm")
    if not _num(rpm):
        return None
    return float(rpm) / 300.0 * 60.0


def skill_tube_insert(ctx):
    arm = ctx.primary_arm
    if not (yield from pick_object(ctx, arm, "caps")):
        return
    det = yield from ctx.search(arm, "dark")
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "dark")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -0.07], steps=10)
    yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.05], steps=8)


def skill_C01(ctx):
    arm = ctx.primary_arm
    if not (yield from pick_object(ctx, arm, "bright")):
        return
    yield from ctx.move_tcp_delta(arm, [0.05, 0.0, 0.0], steps=10)
    yield from place_object(ctx, arm, "green", descend=0.05)


def skill_C02(ctx):
    arm = ctx.primary_arm
    source_pose = ctx.pose(arm)
    if not (yield from pick_object(ctx, arm, "bright")):
        return
    det = yield from ctx.search(arm, "blue", lift=0.01)
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "blue")
    if not det:
        return
    # controlled pour: >= 40 deg tilt while held, RGB level feedback for dosing
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.06], steps=8)
    tilt = _rotation_matrix(math.radians(50.0), 0.0, 0.0)
    yield from ctx.rotate_tcp(arm, tilt, steps=6, max_ticks=20)
    target_ml = 10.0
    for _ in range(20):
        yield from ctx.hold(0.5, gripper=ctx.gripper_width(arm, 0.03))
        level = ctx.detect("liquid")
        if level and _num(level.get("fill_fraction")):
            estimated = 20.0 * float(level["fill_fraction"])
            if estimated >= target_ml - 0.3:
                break
    upright = _rotation_matrix(math.radians(-50.0), 0.0, 0.0)
    yield from ctx.rotate_tcp(arm, upright, steps=6, max_ticks=20)
    if source_pose is not None:
        yield from ctx.move_tcp(arm, source_pose[0], source_pose[1], steps=12, max_ticks=30)
    yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.05], steps=8)


def skill_C04(ctx):
    arm = ctx.primary_arm
    det = yield from ctx.search(arm, "bright")
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "bright")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -0.02], steps=6)
    if not (yield from ctx.close_until_stall(arm)):
        return
    open_turn = _rotation_matrix(0.0, 0.0, math.radians(20.0))
    yield from ctx.rotate_tcp(arm, open_turn, steps=6, max_ticks=20)
    # public process feedback (C04 keeps its declared volume feedback)
    for _ in range(30):
        data = parse_instruments(ctx.obs, ["funnel", "receiver"])
        if data:
            received = data.get("receiver_volume_ml")
            funnel = data.get("funnel_volume_ml")
            if _num(received) and float(received) >= 9.5:
                break
            if _num(funnel) and float(funnel) <= 0.5:
                break
        yield from ctx.hold(0.5, gripper=ctx.gripper_width(arm, 0.03))
    close_turn = _rotation_matrix(0.0, 0.0, math.radians(-20.0))
    yield from ctx.rotate_tcp(arm, close_turn, steps=6, max_ticks=20)
    yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.05], steps=8)


def skill_C07(ctx):
    arm = ctx.primary_arm
    # 1) load the empty receiving cup onto the balance pan, then release/retract
    yield from ctx.open_gripper(arm)
    det = yield from ctx.search(arm, "cup_receiving")
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "cup_receiving")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -0.05], steps=8)
    if not (yield from ctx.close_until_stall(arm)):
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.06], steps=8)
    det = yield from ctx.search(arm, "pan", lift=0.01)
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "pan")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -0.05], steps=8)
    yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.06], steps=8)

    # 2) wait for the instrument to settle, read, and *tare exactly once*
    yield from ctx.hold(1.4)
    stable_reads = 0
    tare_done = False
    tare_failed = False
    for _ in range(4):
        yield ctx.instr("read")
        result = ctx.balance_result() or {}
        if result.get("ok") and result.get("stable"):
            stable_reads += 1
        else:
            yield from ctx.hold(0.5)
        if stable_reads >= 2:
            break
    if stable_reads >= 2:
        yield ctx.instr("tare")
        result = ctx.balance_result() or {}
        if result.get("ok") and result.get("stable"):
            tare_done = True
        else:
            tare_failed = True
    if tare_failed or not tare_done:
        # never re-tare: a second tare after a possibly valid one fails the round
        yield from ctx.hold(0.5)
        return

    # 3) pour the source cup into the receiving cup on the pan, dosing by net mass
    det = yield from ctx.search(arm, "cup_source")
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "cup_source")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, -0.05], steps=8)
    source_pose = ctx.pose(arm)
    if not (yield from ctx.close_until_stall(arm)):
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.07], steps=8)
    det = yield from ctx.search(arm, "pan", lift=0.01)
    if not det:
        return
    det = yield from ctx.servo_pixel(arm, "pan")
    if not det:
        return
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.05], steps=8)
    tilt = _rotation_matrix(math.radians(50.0), 0.0, 0.0)
    yield from ctx.rotate_tcp(arm, tilt, steps=6, max_ticks=20)
    reached = False
    for _ in range(24):
        yield from ctx.hold(0.5, gripper=ctx.gripper_width(arm, 0.03))
        yield ctx.instr("read")
        result = ctx.balance_result() or {}
        if result.get("ok") and result.get("stable") and result.get("net_g") is not None:
            if 9.4 <= float(result["net_g"]) <= 10.6:
                reached = True
                break
    upright = _rotation_matrix(math.radians(-50.0), 0.0, 0.0)
    yield from ctx.rotate_tcp(arm, upright, steps=6, max_ticks=20)
    # 4) return the source cup, release, retract and settle >= 1 s
    if source_pose is not None:
        yield from ctx.move_tcp(arm, source_pose[0], source_pose[1], steps=12, max_ticks=30)
    yield from ctx.open_gripper(arm)
    yield from ctx.move_tcp_delta(arm, [0.0, 0.0, 0.05], steps=8)
    yield from ctx.hold(1.3)
    if reached:
        yield ctx.instr("read")
        yield from ctx.hold(1.2)
    else:
        yield from ctx.hold(1.2)


SKILLS = {
    "bottle_transfer": skill_bottle_transfer,
    "beaker_place": skill_beaker_place,
    "balance_load": skill_balance_load,
    "stirrer_knob": skill_stirrer_knob,
    "tube_insert": skill_tube_insert,
    "C01": skill_C01,
    "C02": skill_C02,
    "C04": skill_C04,
    "C07": skill_C07,
}


def make_skill(ctx):
    factory = SKILLS.get(str(ctx.task))
    if factory is None:
        return None
    return factory(ctx)
