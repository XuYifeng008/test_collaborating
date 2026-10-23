"""Adaptive stirrer-knob policy (franka single arm) for the invitation pilot.

The offline plan rotates the gripper about world +Z in 30 x 1 deg increments
(0.35 s each, 0.05 rad/s) while the TCP stays on the knob grasp centre
(0.30, -0.08, 0.84 m).  At run time the policy closes the jaws until the
fingers are blocked by the knob, squeezes a little deeper, feeds the rotation
segments while reading instruments.stirrer.setpoint_rpm (1 deg = 5 rpm),
re-grips once on stalls, then releases, retracts >= 0.11 m and finishes.
Standard library only.
"""

ARM = "arm"
TASK_ID = "stirrer_knob"
ROBOT = "franka"

APPROACH = [{"positions": [0.1490740186358649, -0.2070251964526743, 0.05199602918286735, -2.205270006095653, -0.027234330121832705, 2.02999041938721, 0.4805009889871264], "gripper_width_m": 0.08, "steps": 90}, {"positions": [0.29814803729720085, 0.035940028628235976, 0.1039920583408062, -2.260521320174704, -0.05446863894337588, 2.3099808387744196, 0.1810020065844823], "gripper_width_m": 0.08, "steps": 90}, {"positions": [0.44722205595853687, 0.2789052537091463, 0.15598808749874504, -2.3157726342537552, -0.08170294776491906, 2.5899712581616297, -0.11849697581816188], "gripper_width_m": 0.08, "steps": 90}]
DESCEND = [{"positions": [0.46893663143616493, 0.4256550770052716, 0.12579893222231117, -2.2990808099007545, -0.1265865802629206, 2.7187608741900386, -0.08624365709853334], "gripper_width_m": 0.08, "steps": 45}]
ROTATE = [{"positions": [0.4652794906234523, 0.4259004010866808, 0.12909465855043278, -2.2989816976678665, -0.12994025873782922, 2.71858776194847, -0.10129755107447021], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.46159740285168627, 0.42611917645335984, 0.1324027764663308, -2.2988991718488725, -0.1332771759388747, 2.718394494284227, -0.11638225950592625], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.45791601223219547, 0.4263434719979954, 0.13571059557357176, -2.298814679073078, -0.13661424606272002, 2.7181961901778977, -0.13146720254382913], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4542354204686987, 0.4265734250803462, 0.13901806458540347, -2.298728115846542, -0.13995152616059706, 2.717992866861445, -0.14655229423198837], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.45055564913931767, 0.42680904499363204, 0.1423251734162369, -2.298639482853735, -0.14328901964510418, 2.7177845159112057, -0.16163753974169168], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.44687671967152137, 0.4270503406866202, 0.1456319120271868, -2.298548781358285, -0.14662672962213769, 2.717571128714369, -0.17672294466362887], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4431986536199609, 0.42729732130651704, 0.14893827027948697, -2.298456012665911, -0.14996465906793244, 2.7173526964637507, -0.19180851471664043], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.43952147267054903, 0.42754999620068096, 0.1522442379314413, -2.298361178122376, -0.15330281082647831, 2.717129210158028, -0.20689425574976292], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.43584519864351695, 0.4278083749159197, 0.15554980463590948, -2.2982642791141297, -0.15664118760626564, 2.7169006606023784, -0.2219801737453136], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.43216985349646386, 0.428072467197734, 0.15885495993779034, -2.298165317068977, -0.15997979197700904, 2.7166670384091267, -0.23706627482199144], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4284954593274113, 0.42834228298955107, 0.16215969327149135, -2.29806429345676, -0.16331862636636008, 2.716428333998436, -0.2521525652379786], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.42482203837785765, 0.42861783243192686, 0.16546399395838948, -2.297961209790055, -0.1666576930566056, 2.716184537599016, -0.2672390513940521], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4211496130358322, 0.42889912586171347, 0.1687678512042848, -2.297856067624889, -0.1699969941813477, 2.7159356392488503, -0.28232573983670284], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4174782058389538, 0.42918617381121116, 0.17207125409684107, -2.297748868561461, -0.17333653172217206, 2.715681628795957, -0.2974126372612567], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4138078394774857, 0.429478987007284, 0.17537419160301726, -2.2976396142448845, -0.17667630750529986, 2.7154224958991775, -0.3124997505150073], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4101385367973951, 0.42977757637045105, 0.17867665256648962, -2.297528306365945, -0.18001632319822455, 2.7151582300289867, -0.3275870866003518], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4064703208034112, 0.4300819530139403, 0.1819786257050642, -2.29741494666187, -0.18335658030633248, 2.7148888204683352, -0.342674652677934], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.4028032146620836, 0.4303921282427211, 0.18528009960807706, -2.2972995369171114, -0.18669708016950806, 2.7146142563135185, -0.3577624560697938], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.39913724170484155, 0.4307081135525021, 0.1885810627337849, -2.2971820789641417, -0.19003782395872476, 2.714334526475076, -0.37285050426252175], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.39547242543105227, 0.43102992062869283, 0.19188150340674698, -2.297062574684274, -0.19337881267261767, 2.7140496196787227, -0.3879388049104218], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.39180878951107934, 0.4313575613453387, 0.19518140981519427, -2.29694102600848, -0.19672004713404184, 2.713759524466307, -0.40302736583867754], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.3881463577893416, 0.4316910477640203, 0.1984807700083884, -2.2968174349182404, -0.2000615279866151, 2.713464229196807, -0.4181161950465241], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.3844851542873683, 0.4320303921327131, 0.20177957189397333, -2.2966918034463917, -0.20340325569124051, 2.7131637220473497, -0.43320530071042906], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.3808252032068564, 0.4323756068846218, 0.20507780323531, -2.2965641336780025, -0.20674523052261903, 2.7128579910142756, -0.4482946911872733], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.3771665289327257, 0.43272670463696994, 0.20837545164880777, -2.296434427751252, -0.21008745256574046, 2.7125470239142255, -0.46338437501754215], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.37350915603616897, 0.433083698189754, 0.21167250460123999, -2.2963026878583275, -0.21342992171235875, 2.712230808385269, -0.4784743609285192], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.36985310927770654, 0.43344660052446465, 0.2149689494070506, -2.296168916246341, -0.2167726376574545, 2.71190933188807, -0.4935646578374839], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.3661984136102328, 0.43381542480276386, 0.21826477322565083, -2.2960331152182456, -0.22011559989567572, 2.711582581707081, -0.5086552748549157], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.3625450941820629, 0.4341901843651219, 0.22155996305870415, -2.2958952871337837, -0.22345880771776594, 2.7112505449517865, -0.5237462212877019], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.358893176339976, 0.43457089272942023, 0.22485450574740112, -2.2957554344104296, -0.22680226020697328, 2.7109132085579724, -0.538837506642349], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}]
RELEASE = [{"positions": [0.358893176339976, 0.43457089272942023, 0.22485450574740112, -2.2957554344104296, -0.22680226020697328, 2.7109132085579724, -0.538837506642349], "gripper_width_m": 0.06, "steps": 120}, {"positions": [0.358893176339976, 0.43457089272942023, 0.22485450574740112, -2.2957554344104296, -0.22680226020697328, 2.7109132085579724, -0.538837506642349], "gripper_width_m": 0.08, "steps": 120}]
RETRACT = [{"positions": [0.3000045728270151, 0.17514693138664605, 0.3071577144170182, -2.3066476682312893, -0.08498761281724937, 2.4719937055313745, -0.6395517829148557], "gripper_width_m": 0.08, "steps": 78}]

GRASP_Z_M = 0.84
GRASP_XY_TOL_M = 0.03
GRASP_Z_TOL_M = 0.03
RPM_TARGET = 145.0
CLOSE_STEP = 0.030
CLOSE_STEPS = 120
MIN_WIDTH = 0.006
STALL_SEGMENTS = 5
MAX_REGRIPS = 1


def _one(action, width):
    return {
        "arms": {ARM: {"positions": action["positions"],
                        "gripper_width_m": action.get("gripper_width_m", width)}},
        "steps": int(action["steps"]),
    }


class Policy:
    def reset(self, instruction):
        self.enabled = (instruction.get("task_id") == TASK_ID
                        and instruction.get("robot_profile") == ROBOT
                        and ARM in instruction.get("arms", {}))
        self.approach_i = 0
        self.phase = "approach"
        self.retries = 0
        self.close_target = 0.078
        self.last_width = None
        self.blocks = 0
        self.grip_width = 0.05
        self.rot_i = 0
        self.wait = 0
        self.stall = 0
        self.last_rpm = 0.0
        self.regrips = 0
        self.release_i = 0
        self.reopen_target = None

    def _start_release(self):
        self.phase = "release"
        self.release_i = 0
        return _one(RELEASE[0], self.grip_width)

    def _grip_logic(self, width):
        self.close_target = max(MIN_WIDTH, self.close_target - CLOSE_STEP)
        action = {"arms": {ARM: {"positions": DESCEND[0]["positions"],
                                 "gripper_width_m": self.close_target}},
                  "steps": CLOSE_STEPS}
        if self.last_width is not None:
            if abs(width - self.last_width) < 0.0006 and self.close_target < 0.06:
                self.blocks += 1
            else:
                self.blocks = 0
        self.last_width = width
        if self.blocks >= 2:
            self.grip_width = max(MIN_WIDTH, min(0.06, width - 0.003))
            self.phase = "squeeze"
            return action
        if self.close_target <= MIN_WIDTH:
            self.grip_width = max(MIN_WIDTH, width - 0.003)
            self.phase = "squeeze"
        return action

    def act(self, observation):
        if not self.enabled:
            return {"finish": True}
        if self.wait > 0:
            self.wait -= 1
            return {"arms": {}, "steps": 2}

        instr = observation.get("instruments", {}).get("stirrer", {}) or {}
        rpm = instr.get("setpoint_rpm") or 0.0
        state = observation["proprioception"][ARM]
        tcp = state["tcp_position_m"]
        width = state["gripper_width_m"]

        if self.phase == "approach":
            action = APPROACH[self.approach_i]
            self.approach_i += 1
            if self.approach_i >= len(APPROACH):
                self.phase = "descend"
            return _one(action, 0.08)

        if self.phase == "descend":
            self.phase = "verify"
            return _one(DESCEND[0], 0.08)

        if self.phase == "verify":
            dx = tcp[0] - 0.30
            dy = tcp[1] + 0.08
            dz = tcp[2] - GRASP_Z_M
            ok = abs(dz) <= GRASP_Z_TOL_M and (dx * dx + dy * dy) ** 0.5 <= GRASP_XY_TOL_M
            if not ok and self.retries < 2:
                self.retries += 1
                self.wait = 3
                return _one(DESCEND[0], 0.08)
            if not ok:
                self.phase = "abort"
                return _one(RETRACT[0], 0.08)
            self.phase = "close"
            return {"arms": {}, "steps": 4}

        if self.phase == "close":
            return self._grip_logic(width)

        if self.phase == "squeeze":
            self.phase = "rotate"
            self.wait = 3
            return {"arms": {ARM: {"positions": DESCEND[0]["positions"],
                                     "gripper_width_m": self.grip_width}},
                    "steps": CLOSE_STEPS}

        if self.phase == "regrip_open":
            self.phase = "regrip_wait"
            self.wait = 3
            return {"arms": {ARM: {"positions": DESCEND[0]["positions"],
                                     "gripper_width_m": self.reopen_target}},
                    "steps": 60}

        if self.phase == "regrip_wait":
            self.close_target = max(0.02, width - 0.002)
            self.blocks = 0
            self.last_width = None
            self.phase = "close"
            return {"arms": {}, "steps": 4}

        if self.phase == "rotate":
            if rpm >= RPM_TARGET or self.rot_i >= len(ROTATE):
                return self._start_release()
            if abs(rpm - self.last_rpm) < 0.4:
                self.stall += 1
            else:
                self.stall = 0
            self.last_rpm = rpm
            if self.stall >= STALL_SEGMENTS:
                if self.regrips < MAX_REGRIPS:
                    self.regrips += 1
                    self.stall = 0
                    self.reopen_target = min(0.08, max(0.03, width + 0.006))
                    self.phase = "regrip_open"
                    return {"arms": {ARM: {"positions": DESCEND[0]["positions"],
                                             "gripper_width_m": self.reopen_target}},
                            "steps": 60}
                return self._start_release()
            action = ROTATE[self.rot_i]
            self.rot_i += 1
            return {"arms": {ARM: {"positions": action["positions"],
                                     "gripper_width_m": self.grip_width}},
                    "steps": int(action["steps"])}

        if self.phase == "release":
            if self.release_i >= len(RELEASE):
                self.phase = "retract"
                return _one(RETRACT[0], 0.08)
            action = RELEASE[self.release_i]
            self.release_i += 1
            return _one(action, self.grip_width)

        if self.phase in ("retract", "abort"):
            self.phase = "done"
            return _one(RETRACT[0], 0.08)

        return {"finish": True}
