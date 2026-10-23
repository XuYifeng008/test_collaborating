"""Adaptive stirrer-knob policy (dual_piper right arm) for the invitation pilot.

Offline plan: joint targets that put the right-arm TCP on the speed-knob grasp
centre (0.3, -0.08, 0.84 m) and rotate the gripper about world +Z in 1.5 deg
increments while keeping the TCP fixed on the knob axis.  At run time the
policy (1) closes the gripper until the fingers are blocked by the knob,
(2) feeds small rotations back-to-back while reading the encoder
(instruments.stirrer.setpoint_rpm; 0..60 deg maps to 0..300 rpm, so 30 deg =
150 rpm), (3) stops near 29 deg, releases, then retracts >= 0.11 m and finishes.
No third-party packages are used.
"""

ARM = 'right'
TASK_ID = 'stirrer_knob'
ROBOT = 'dual_piper'

APPROACH = [{"positions": [0.03486531223105153, 2.3617278309653664, -1.570072321443826, 1.0327003296206049e-05, 0.878996122950887, -1.5359326039386358], "gripper_width_m": 0.08, "steps": 43}]
DESCEND = [{"positions": [0.03486531072571333, 2.501739258950877, -1.573932939726305, 1.1757988864099242e-05, 0.742841784743163, -1.5359346779742162], "gripper_width_m": 0.08, "steps": 43}]
ROTATE = [{"positions": [0.035064352670079506, 2.5017646154758046, -1.5739648846610832, -0.0004802340963351941, 0.7428447187727925, -1.561548666411164], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03523820063497074, 2.5017575158261844, -1.5739480216891186, -0.0009638076213344603, 0.7428226402604353, -1.5871965076780896], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03541176274764765, 2.501744630119439, -1.5739175892475041, -0.0014467702775503727, 0.7427843475225653, -1.612845071253136], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03558497884774863, 2.5017264722475296, -1.573874724329172, -0.001928840439804225, 0.7427305222016822, -1.6384946091689394], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03575773276230005, 2.5017030714210877, -1.5738194942899726, -0.0024097186021928636, 0.7426612224553542, -1.664145448591919], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03592990840792654, 2.501674444639106, -1.5737519388406693, -0.0028891056835437744, 0.7425764947444551, -1.6897979164592467], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03610139006360854, 2.501640612041511, -1.5736721050611764, -0.0033667032418990255, 0.7424763949800214, -1.7154523390493264], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.036272062446965334, 2.5016015974115375, -1.5735800485484288, -0.0038422136054241315, 0.7423609892053968, -1.7411090418425292], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03644181078734262, 2.50155742817517, -1.5734758334155148, -0.004315340002430022, 0.7422303535811003, -1.7667683493857926], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.0366105208985677, 2.501508135380952, -1.5733595322460068, -0.004785786691894698, 0.7420845743403078, -1.7924305851565647], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03677807925142997, 2.5014537536764756, -1.5732312260407761, -0.005253259094585052, 0.7419237477375166, -1.8180960714258705], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.036944373045853664, 2.501394321282144, -1.5730910041586057, -0.005717463924847868, 0.7417479799911628, -1.8437651291203945], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03710929028272644, 2.5013298799622308, -1.572938964250679, -0.006178109323136545, 0.7415573872202459, -1.8694380776834838], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03727271983535496, 2.501260474993285, -1.5727752121890277, -0.006634904989336617, 0.7413520953749868, -1.8951152349349774], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03743455152050374, 2.501186155129898, -1.5725998619889854, -0.007087562316950649, 0.7411322401615504, -1.9207969169297732], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.037594676168990246, 2.5011069725678685, -1.5724130357257216, -0.00753579452819975, 0.740897966960862, -1.9464834378150502], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.037752985695795285, 2.501022982904806, -1.572214863444935, -0.007979316810094828, 0.740649430741552, -1.9721751096860656], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03790937316965749, 2.500934245098209, -1.5720054830677805, -0.00841784645152753, 0.7403867959670631, -1.9978722424404514], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03806373288211037, 2.500840821421054, -1.5717850402901137, -0.008851102981425892, 0.740110236496966, -2.023575143630954], "dtheta_deg": 1.5, "steps": 11}, {"positions": [0.03821596041593495, 2.5007427774149433, -1.571553688476147, -0.00927880830801595, 0.7398199354825132, -2.049284118316536], "dtheta_deg": 1.5, "steps": 11}]
RELEASE = [{"positions": [0.03821596041593495, 2.5007427774149433, -1.571553688476147, -0.00927880830801595, 0.7398199354825132, -2.049284118316536], "gripper_width_m": 0.06, "steps": 120}, {"positions": [0.03821596041593495, 2.5007427774149433, -1.571553688476147, -0.00927880830801595, 0.7398199354825132, -2.049284118316536], "gripper_width_m": 0.08, "steps": 120}]
RETRACT = [{"positions": [0.03818982435724528, 2.2635641439170313, -1.6047629321835908, -0.00737912972985145, 1.0101981018169262, -2.0522426109615353], "gripper_width_m": 0.08, "steps": 82}]

GRASP_Z_M = 0.84
GRASP_XY_TOL_M = 0.02
GRASP_Z_TOL_M = 0.02
RPM_TARGET = 145.0        # ~= 29 deg (5 rpm per degree), target band 125..175
CLOSE_STEP = 0.004        # commanded jaw width decrease per action
CLOSE_STEPS = 14          # physics steps per close action (0.06 m/s slew fits)
MIN_WIDTH = 0.006


def _arm_state(obs):
    return obs["proprioception"][ARM]


class Policy:
    def reset(self, instruction):
        self.enabled = (instruction.get("task_id") == TASK_ID
                        and instruction.get("robot_profile") == ROBOT
                        and ARM in instruction.get("arms", {}))
        self.phase = "approach"
        self.close_target = 0.078
        self.last_width = None
        self.blocks = 0
        self.grip_width = 0.05
        self.rot_i = 0
        self.wait = 0
        self.stall = 0
        self.last_rpm = None

    # ---- helpers -------------------------------------------------------
    def _one(self, action):
        return {
            "arms": {ARM: {"positions": action["positions"],
                            "gripper_width_m": action.get("gripper_width_m", self.grip_width)}},
            "steps": int(action["steps"]),
        }

    def _retract_and_finish(self, obs):
        self.phase = "retract"
        return self._one(RETRACT[0])

    def act(self, observation):
        if not self.enabled:
            return {"finish": True}
        if self.wait > 0:
            self.wait -= 1
            return {"arms": {}, "steps": 2}

        instr = observation.get("instruments", {}).get("stirrer", {}) or {}
        rpm = instr.get("setpoint_rpm") or 0.0
        state = _arm_state(observation)
        tcp = state["tcp_position_m"]
        width = state["gripper_width_m"]

        if self.phase == "approach":
            self.phase = "descend"
            return self._one(APPROACH[0])

        if self.phase == "descend":
            self.phase = "verify"
            return self._one(DESCEND[0])

        if self.phase == "verify":
            dx = tcp[0] - 0.30
            dy = tcp[1] + 0.08
            dz = tcp[2] - GRASP_Z_M
            if abs(dz) > GRASP_Z_TOL_M or (dx * dx + dy * dy) ** 0.5 > GRASP_XY_TOL_M:
                self.phase = "abort"
                return self._one(RETRACT[0])
            self.phase = "close"
            return {"arms": {}, "steps": 4}

        if self.phase == "close":
            self.close_target = max(MIN_WIDTH, self.close_target - CLOSE_STEP)
            action = {"arms": {ARM: {"positions": DESCEND[0]["positions"],
                                     "gripper_width_m": self.close_target}},
                      "steps": CLOSE_STEPS}
            if self.last_width is not None:
                if abs(width - self.last_width) < 0.0008 and self.close_target < 0.06:
                    self.blocks += 1
                else:
                    self.blocks = 0
            self.last_width = width
            if self.blocks >= 2:
                self.grip_width = min(0.06, max(MIN_WIDTH, width - 0.0015))
                self.phase = "rotate"
                self.wait = 2
            elif self.close_target <= MIN_WIDTH:
                self.grip_width = MIN_WIDTH
                self.phase = "rotate"
            return action

        if self.phase == "rotate":
            if rpm >= RPM_TARGET or self.rot_i >= len(ROTATE):
                self.phase = "release"
                self.grip_width = max(self.grip_width, 0.06)
                return self._one(RELEASE[0])
            if self.last_rpm is not None and abs(rpm - self.last_rpm) < 0.5:
                self.stall += 1
            else:
                self.stall = 0
            self.last_rpm = rpm
            if self.stall >= 12:      # encoder never moved: un-grip, release, give up
                self.phase = "release"
                return self._one(RELEASE[0])
            action = ROTATE[self.rot_i]
            self.rot_i += 1
            return {"arms": {ARM: {"positions": action["positions"],
                                     "gripper_width_m": self.grip_width}},
                    "steps": int(action["steps"])}

        if self.phase == "release":
            self.release_i = getattr(self, "release_i", 0)
            if self.release_i >= len(RELEASE):
                self.phase = "retract"
                return self._one(RETRACT[0])
            action = RELEASE[self.release_i]
            self.release_i += 1
            return self._one(action)

        if self.phase == "retract":
            self.phase = "done"
            return self._one(RETRACT[0])

        if self.phase == "abort":
            self.phase = "done"
            return self._one(RETRACT[0])

        return {"finish": True}
