"""Minimal-motion franka probe: nudge joint4 by +0.05 rad, hold, finish."""


class Policy:
    def reset(self, instruction):
        self.enabled = instruction.get("robot_profile") == "franka"
        self.n = 0

    def act(self, observation):
        if not self.enabled:
            return {"finish": True}
        self.n += 1
        if self.n >= 4:
            return {"finish": True}
        q = list(observation["proprioception"]["arm"]["arm_joint_positions"])
        q[3] += 0.05
        return {"arms": {"arm": {"positions": q, "gripper_width_m": 0.08}}, "steps": 60}
