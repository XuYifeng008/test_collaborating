"""Adaptive stirrer-knob policy v2 (dual_piper right arm).

The offline plan rotates the gripper about world +Z in 30 x 1 deg increments
(0.35 s each, 0.05 rad/s) while the TCP stays on the knob grasp centre
(0.30, -0.08, 0.84 m).  At run time the policy closes the jaws until the
fingers are blocked by the knob, squeezes a little deeper, then feeds the
rotation segments while reading instruments.stirrer.setpoint_rpm
(0..60 deg -> 0..300 rpm, so 1 deg = 5 rpm).  If the encoder stalls for several
segments it opens/re-grips the knob once or twice before giving up, then
releases, retracts >= 0.11 m and finishes.  Stdlib only.
"""

ARM = 'right'
TASK_ID = 'stirrer_knob'
ROBOT = 'dual_piper'

APPROACH = [{"positions": [0.03486531223105153, 2.3617278309653664, -1.570072321443826, 1.0327003296206049e-05, 0.878996122950887, -1.5359326039386358], "gripper_width_m": 0.08, "steps": 43}]
DESCEND = [{"positions": [0.03486531072571333, 2.501739258950877, -1.573932939726305, 1.1757988864099242e-05, 0.742841784743163, -1.5359346779742162], "gripper_width_m": 0.08, "steps": 43}]
ROTATE = [{"positions": [0.03499801106069836, 2.5017661050344273, -1.5739683659487693, -0.00031625109118619654, 0.7428490840258706, -1.5530106551031249], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035113957529855515, 2.5017632859422325, -1.573961621831545, -0.0006387595875525014, 0.7428397584816269, -1.5701090796274055], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03522979868539029, 2.501757595167089, -1.5739481809681737, -0.0009610812434790539, 0.7428228306575547, -1.5872077453199651], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03534553760311581, 2.5017495474096885, -1.5739291828580746, -0.001283139401286045, 0.7427989746835869, -1.6043066987473926], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03546113986422968, 2.501739161938573, -1.573904671599355, -0.0016048452207942203, 0.7427682206488616, -1.6214060368681253], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035576570952087584, 2.501726442562494, -1.5738746560655252, -0.0019261098702502912, 0.7427305783454988, -1.6385058567734954], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03569179639595773, 2.50171139327461, -1.57383914558968, -0.0022468446009818797, 0.7426860588327949, -1.6556062554710944], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035806781782791626, 2.501694018778378, -1.573798151165751, -0.0025669607653051765, 0.7426346751629276, -1.6727073298640094], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035921492766954714, 2.5016743245037514, -1.5737516854855556, -0.0028863698335453896, 0.7425764424020947, -1.6898091767330965], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03603589507988046, 2.501652316605953, -1.5736997629360352, -0.00320498341106814, 0.742511377627369, -1.7069118927192901], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03614995453970503, 2.501628001963422, -1.5736423995946047, -0.00352271325534646, 0.7424394999222047, -1.7240155743058674], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.0362636370608844, 2.501601388175492, -1.5735796132239064, -0.0038394712930679455, 0.742360830371392, -1.741120317800649], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.036376908663793346, 2.5015724835598285, -1.5735114232660152, -0.004155169637286324, 0.7422753920554787, -1.7582262193181366], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03648973548429997, 2.501541297149624, -1.5734378508360933, -0.004469720604621812, 0.7421832100446565, -1.7753333747615785], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.0366020837833178, 2.501507838690556, -1.5733589187155, -0.004783036732514293, 0.7420843113921176, -1.7924418798049575], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.036713919956331706, 2.501472118637498, -1.573274651344359, -0.005095030796533251, 0.7419787251268876, -1.8095518298748954], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03682521054289562, 2.5014341481510027, -1.5731850748135872, -0.0054056158277486395, 0.7418664822461244, -1.8266633201324678], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03693592223609979, 2.50139393909354, -1.573090216856387, -0.0057147051301663365, 0.741747615706897, -1.8437764454549253], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037046021892007286, 2.501351504025501, -1.5729901068392005, -0.006022212298232038, 0.7416221604174351, -1.8608913004173113], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037155476539055085, 2.501306856200979, -1.5728847757521442, -0.006328051234407169, 0.7414901532278583, -1.8780079792739783], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03726425338741969, 2.5012600095633086, -1.57277425619891, -0.006632136166820374, 0.7413516329203836, -1.895126575939989], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03737231983834358, 2.5012109787403802, -1.5726585823861492, -0.006934381666997876, 0.7412066401990146, -1.9122471839724038], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037479643493423705, 2.5011597790397224, -1.5725377901123336, -0.0072347026676759865, 0.7410552176787122, -1.9293698965514476], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037586192163855024, 2.501106426443371, -1.5724119167561128, -0.007533014480698904, 0.7408974098740504, -1.9464948064615502], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03769193387963019, 2.501050937602502, -1.5722810012641546, -0.007829232815004717, 0.7407332631873564, -1.9636220060722596], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03779683689869426, 2.5009933298318505, -1.572145084138485, -0.008123273794702297, 0.7405628258963469, -1.9807515873190178], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03790086971604975, 2.5009336211039144, -1.5720042074233334, -0.008415053977241826, 0.7403861481412456, -1.9978836416838026], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.038004001072809636, 2.5008718300429327, -1.5718584146914778, -0.00870449037168143, 0.7402032819114022, -2.0150182601756272], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.0381061999652005, 2.500807975918661, -1.571707751030108, -0.0089915004570519, 0.7400142810314054, -2.032155533310894], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03820743565350759, 2.500742078639933, -1.5715522630262035, -0.009276002200822019, 0.7398192011466913, -2.049295551093603], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}]
RELEASE = [{"positions": [0.03820743565350759, 2.500742078639933, -1.5715522630262035, -0.009276002200822019, 0.7398192011466913, -2.049295551093603], "gripper_width_m": 0.06, "steps": 120}, {"positions": [0.03820743565350759, 2.500742078639933, -1.5715522630262035, -0.009276002200822019, 0.7398192011466913, -2.049295551093603], "gripper_width_m": 0.08, "steps": 120}]
RETRACT = [{"positions": [0.038189824357245196, 2.2635641439170313, -1.6047629321835908, -0.00737912972985145, 1.0101981018169262, -2.0522426109615357], "gripper_width_m": 0.08, "steps": 82}]

GRASP_Z_M = 0.84
GRASP_XY_TOL_M = 0.03
GRASP_Z_TOL_M = 0.03
RPM_TARGET = 145.0        # ~= 29 deg; target band 125..175 rpm
CLOSE_STEP = 0.030
CLOSE_STEPS = 120
MIN_WIDTH = 0.006
STALL_SEGMENTS = 5
MAX_REGRIPS = 1


def _arm_state(obs):
    return obs["proprioception"][ARM]


class Policy:
    def reset(self, instruction):
        self.enabled = (instruction.get("task_id") == TASK_ID
                        and instruction.get("robot_profile") == ROBOT
                        and ARM in instruction.get("arms", {}))
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

    def _one(self, action, width=None):
        return {
            "arms": {ARM: {"positions": action["positions"],
                            "gripper_width_m": action.get("gripper_width_m", width)}},
            "steps": int(action["steps"]),
        }

    def _start_release(self):
        self.phase = "release"
        self.release_i = 0
        return self._one(RELEASE[0])

    def _grip_logic(self, width):
        """Return action for the close phase, advancing state when blocked."""
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
            ok = abs(dz) <= GRASP_Z_TOL_M and (dx * dx + dy * dy) ** 0.5 <= GRASP_XY_TOL_M
            if not ok and self.retries < 2:
                self.retries += 1
                self.wait = 3
                return self._one(DESCEND[0])
            if not ok:
                self.phase = "abort"
                return self._one(RETRACT[0])
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
                    return self._regrip_open_action()
                return self._start_release()
            action = ROTATE[self.rot_i]
            self.rot_i += 1
            return {"arms": {ARM: {"positions": action["positions"],
                                     "gripper_width_m": self.grip_width}},
                    "steps": int(action["steps"])}

        if self.phase == "release":
            if self.release_i >= len(RELEASE):
                self.phase = "retract"
                return self._one(RETRACT[0])
            action = RELEASE[self.release_i]
            self.release_i += 1
            return self._one(action)

        if self.phase in ("retract", "abort"):
            self.phase = "done"
            return self._one(RETRACT[0])

        return {"finish": True}

    def _regrip_open_action(self):
        return {"arms": {ARM: {"positions": DESCEND[0]["positions"],
                                 "gripper_width_m": self.reopen_target}},
                "steps": 60}
