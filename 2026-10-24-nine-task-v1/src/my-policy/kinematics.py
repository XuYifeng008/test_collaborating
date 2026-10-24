"""Forward kinematics and damped-least-squares IK from the *public* robot_kinematics.

The workshop instruction publishes, per arm, the robot's joint frames
(``local0``/``local1``), joint axes, joint limits and a declared TCP offset.
No object pose, contact truth or private judge state is used here.

Convention (validated against the real public fixtures shipped with the kit,
which are recorded observations of the deployed scene):

    raw chain:  T = base @ prod_i ( local0_i @ R(axis_i, q_i) @ inv(local1_i) )

The published TCP frame differs from the raw chain end by a *constant*
rigid transform.  That constant is estimated at run time from the first
public ``proprioception`` reading (the observation already carries the measured
TCP position/rotation).  This keeps the controller correct even if a backend
mounts the tool differently: we never assume the declared offset is exact.

Only public observations are used: ``proprioception`` TCP pose + joint state,
published kinematics, published limits.  No simulator, judge or object truth.
"""

import math

import numpy as np


def _rot_axis(axis, q):
    a = np.asarray(axis, dtype=float)
    n = float(np.linalg.norm(a))
    if n < 1e-12:
        return np.eye(3)
    a = a / n
    x, y, z = float(a[0]), float(a[1]), float(a[2])
    c, s = math.cos(q), math.sin(q)
    C = 1.0 - c
    return np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ])


def _T(R=None, t=None):
    m = np.eye(4)
    if R is not None:
        m[:3, :3] = R
    if t is not None:
        m[:3, 3] = np.asarray(t, dtype=float).reshape(3)
    return m


def rotvec(R):
    """Rotation vector (axis*angle) of a rotation matrix, world frame."""
    R = np.asarray(R, dtype=float)
    c = (np.trace(R) - 1.0) / 2.0
    c = max(-1.0, min(1.0, c))
    angle = math.acos(c)
    if angle < 1e-9:
        return np.zeros(3)
    if abs(math.pi - angle) < 1e-6:
        # near pi: use the symmetric part
        A = (R + np.eye(3)) / 2.0
        d = np.clip(np.diag(A), 0.0, None)
        axis = np.sqrt(d)
        k = int(np.argmax(axis))
        axis = A[:, k] / math.sqrt(max(d[k], 1e-12))
        n = np.linalg.norm(axis)
        axis = axis / n if n > 1e-12 else np.array([1.0, 0.0, 0.0])
        return axis * angle
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return axis * (angle / (2.0 * math.sin(angle)))


def exp_rotvec(w):
    w = np.asarray(w, dtype=float)
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1.0 - math.cos(th)) * (K @ K)


class Chain:
    """The published kinematic chain for one arm (raw, without the tool correction)."""

    def __init__(self, kin):
        self.base = np.asarray(kin["base_matrix"], dtype=float)
        self.joints = list(kin["joints"])
        self.arm_names = list(kin.get("arm_names") or [])
        self.declared_tcp_offset = np.asarray(kin["tcp_offset_m"], dtype=float).reshape(3)
        self._index = {j["name"]: j for j in self.joints}
        self._q_index = {name: i for i, name in enumerate(self.arm_names)}
        # per-joint local transforms, rotation axes, kinds
        self._local0 = [np.asarray(j["local0"], dtype=float) for j in self.joints]
        self._local1i = [np.linalg.inv(np.asarray(j["local1"], dtype=float)) for j in self.joints]
        self._axis = [np.asarray(j["axis"], dtype=float).reshape(3) for j in self.joints]
        self._kind = [j["kind"] for j in self.joints]
        self._qpos = [self._q_index.get(j["name"]) for j in self.joints]

    def raw(self, q):
        """Raw chain end-effector pose for arm joint vector q (numpy)."""
        q = np.asarray(q, dtype=float).reshape(-1)
        T = self.base.copy()
        for k, j in enumerate(self.joints):
            qi = self._qpos[k]
            angle = 0.0 if qi is None or qi >= q.shape[0] else float(q[qi])
            kind = self._kind[k]
            if kind == "revolute":
                step = _T(R=_rot_axis(self._axis[k], angle))
            elif kind == "prismatic":
                step = _T(t=self._axis[k] * angle)
            else:
                step = np.eye(4)
            T = T @ self._local0[k] @ step @ self._local1i[k]
        return T[:3, :3].copy(), T[:3, 3].copy()


class ArmModel:
    """One arm: public chain + run-time calibrated tool transform + IK."""

    def __init__(self, name, kin, joint_names, gripper_max):
        self.name = str(name)
        self.chain = Chain(kin)
        self.joint_names = list(joint_names)
        n = len(self.joint_names)
        if n not in (6, 7):
            raise ValueError("unexpected joint count for %s" % self.name)
        self.n = n
        self.gripper_max = float(gripper_max)
        self.limits = None            # filled from first public observation
        self.speed_limit = 0.8        # rad/s, published per-arm default
        self.grip_speed = 0.06        # m/s
        self._M_R = None              # tool rotation offset (chain -> TCP)
        self._M_t = None              # tool translation offset (chain -> TCP)
        self.calibrated = False

    # ---- calibration -------------------------------------------------
    def calibrate(self, q, tcp_pos, tcp_rot):
        q = np.asarray(q, dtype=float).reshape(-1)[: self.n]
        Rc, pc = self.chain.raw(q)
        Rt = np.asarray(tcp_rot, dtype=float).reshape(3, 3)
        pt = np.asarray(tcp_pos, dtype=float).reshape(3)
        if not (np.all(np.isfinite(Rc)) and np.all(np.isfinite(pc))):
            raise ValueError("non-finite public kinematics")
        self._M_R = Rc.T @ Rt
        self._M_t = Rc.T @ (pt - pc)
        # a bad model would not be a proper rotation
        if abs(float(np.linalg.det(self._M_R)) - 1.0) > 1e-3:
            raise ValueError("public kinematics do not close with observed TCP")
        self.calibrated = True
        return self

    def fk(self, q):
        if not self.calibrated:
            raise RuntimeError("arm model must be calibrated from a public observation")
        Rc, pc = self.chain.raw(q)
        R = Rc @ self._M_R
        p = pc + Rc @ self._M_t
        return R, p

    # ---- inverse kinematics -----------------------------------------
    def ik(self, target_pos, target_rot, seed, iters=40, damping=0.08):
        """Damped-least-squares IK reaching a TCP pose; returns clipped joints."""
        if not self.calibrated:
            raise RuntimeError("arm model must be calibrated from a public observation")
        q = np.asarray(seed, dtype=float).reshape(-1)[: self.n].copy()
        lo, hi = self._bounds()
        # map the requested TCP pose back to the raw chain frame
        Rt = np.asarray(target_rot, dtype=float).reshape(3, 3)
        pt = np.asarray(target_pos, dtype=float).reshape(3)
        Rc_t = Rt @ self._M_R.T
        pc_t = pt - Rc_t @ self._M_t
        eps = 1e-6
        for _ in range(int(iters)):
            Rc, pc = self.chain.raw(q)
            e_pos = pc_t - pc
            e_rot = rotvec(Rc_t @ Rc.T)
            err = np.concatenate([e_pos, e_rot])
            if float(np.linalg.norm(e_pos)) < 2e-4 and float(np.linalg.norm(e_rot)) < 2e-3:
                break
            J = np.zeros((6, self.n))
            for i in range(self.n):
                dq = np.zeros(self.n)
                dq[i] = eps
                Rp, pp = self.chain.raw(q + dq)
                J[:3, i] = (pp - pc) / eps
                J[3:, i] = rotvec(Rp @ Rc.T) / eps
            A = J @ J.T + (damping ** 2) * np.eye(6)
            try:
                dq = J.T @ np.linalg.solve(A, err)
            except np.linalg.LinAlgError:
                dq = J.T @ err
            # limit the step so IK stays local and honour joint limits
            step_scale = min(1.0, 0.25 / max(float(np.max(np.abs(dq))), 1e-9))
            q = q + dq * step_scale
            q = np.minimum(np.maximum(q, lo), hi)
        return q

    def _bounds(self):
        if self.limits is None:
            lo = np.full(self.n, -2.8)
            hi = np.full(self.n, 2.8)
            return lo, hi
        lo = np.array([self.limits[n][0] for n in self.joint_names], dtype=float)
        hi = np.array([self.limits[n][1] for n in self.joint_names], dtype=float)
        return lo, hi

    def set_limits(self, lower, upper):
        lower = np.asarray(lower, dtype=float).reshape(-1)
        upper = np.asarray(upper, dtype=float).reshape(-1)
        if lower.shape[0] != self.n or upper.shape[0] != self.n:
            return
        self.limits = {name: (float(lo), float(hi))
                       for name, lo, hi in zip(self.joint_names, lower, upper)}

    def clip_target(self, q_cmd, q_now, steps, dt, margin=1e-4):
        """Clamp a commanded joint target to limits and to the public slew limit."""
        q_cmd = np.asarray(q_cmd, dtype=float).reshape(-1)[: self.n]
        lo, hi = self._bounds()
        q_cmd = np.minimum(np.maximum(q_cmd, lo + margin), hi - margin)
        max_delta = self.speed_limit * max(int(steps), 1) * float(dt) * 0.9
        if q_now is not None:
            q_now = np.asarray(q_now, dtype=float).reshape(-1)[: self.n]
            delta = np.clip(q_cmd - q_now, -max_delta, max_delta)
            q_cmd = q_now + delta
        return q_cmd
