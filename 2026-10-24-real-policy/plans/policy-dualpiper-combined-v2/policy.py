"""Combined dual_piper policy for the lab embodiment invitation pilot.

Two scripted skills are baked from offline IK plans (fixed scene geometry):

* bottle_transfer: replay of the grasp / lift / carry / place joint trajectory for
  bottle_05 from the source basket into the blue collection basket.
* stirrer_knob: adaptive right-arm skill using the slow rotation plan
  (30 x 1 deg @ 0.35 s about +Z around the knob grasp centre 0.30,-0.08,0.84 m);
  at run time it closes the jaws until blocked, reads the stirrer encoder
  (0..60 deg -> 0..300 rpm) to stop near 29 deg, re-grips on stalls, then
  releases and retracts.

Any other task returns finish immediately.  Standard library only.
"""

BOTTLE_ACTIONS = [{"positions": [-0.08127380416023926, 1.9086189512431855, -0.4898401435792347, -0.07521178527753773, -0.6780520645701715, 0.0002932140169573452], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.08701798081851395, 1.8874842413306703, -0.5424178712725441, -0.06518360881172068, -0.48202817994829605, -0.0163265072677468], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.09276215747678862, 1.866349531418155, -0.5949955989658535, -0.055155432345903616, -0.28600429532642047, -0.03294622855245095], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.09850633413506331, 1.8452148215056399, -0.647573326659163, -0.04512725588008656, -0.08998041070454499, -0.04956594983715509], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.104250510793338, 1.8240801115931247, -0.7001510543524724, -0.0350990794142695, 0.1060434739173306, -0.06618567112185923], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.10999468745161269, 1.8029454016806095, -0.7527287820457818, -0.025070902948452434, 0.3020673585392062, -0.08280539240656339], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.11573886410988737, 1.7818106917680943, -0.8053065097390912, -0.015042726482635382, 0.49809124316108155, -0.09942511369126751], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.12148304076816205, 1.760675981855579, -0.8578842374324006, -0.005014550016818317, 0.6941151277829571, -0.11604483497597168], "gripper_width_m": 0.08, "steps": 79}, {"positions": [-0.1243551290972994, 1.7501086268993213, -0.8841731012790554, -4.617839097914578e-07, 0.7921270700938949, -0.12435469561832374], "gripper_width_m": 0.08, "steps": 40}, {"positions": [-0.12435505847071873, 1.9133326353368967, -0.8115407403955244, 5.7836665690961415e-08, 0.5562710229027309, -0.12435505387691284], "gripper_width_m": 0.08, "steps": 95}, {"positions": [-0.12435505887441414, 2.1650373572688193, -0.7943006600246909, 1.0818441101820691e-07, 0.28731307007023243, -0.12435510899540647], "gripper_width_m": 0.08, "steps": 108}, {"positions": [-0.12435505849781464, 2.2738868368061436, -0.810807617620493, 1.6262153611306815e-07, 0.19495707111811275, -0.1243551646055148], "gripper_width_m": 0.08, "steps": 44}, {"positions": [-0.12435505849781464, 2.2738868368061436, -0.810807617620493, 1.6262153611306815e-07, 0.19495707111811275, -0.1243551646055148], "gripper_width_m": 0.05, "steps": 120}, {"positions": [-0.12435505849781464, 2.2738868368061436, -0.810807617620493, 1.6262153611306815e-07, 0.19495707111811275, -0.1243551646055148], "gripper_width_m": 0.0422, "steps": 32}, {"positions": [-0.12435505905494944, 2.0109757156661194, -0.7943847516605541, 7.15649583677138e-08, 0.44146662556125144, -0.12435507005841452], "gripper_width_m": 0.0422, "steps": 106}, {"positions": [-0.12435505858663774, 1.871198779066283, -0.8238640526869359, 5.3286549967399596e-08, 0.610717130228546, -0.12435504851706682], "gripper_width_m": 0.0422, "steps": 68}, {"positions": [0.13603842359765114, 1.872334396366687, -0.8258756141144291, 3.783026851264309e-06, 0.611599895052606, 0.13603484161172555], "gripper_width_m": 0.0422, "steps": 105}, {"positions": [0.37949736998232475, 1.9192375157381805, -0.9086339424985226, -3.3246526732356313e-06, 0.6474404836730787, 0.37950208190716567], "gripper_width_m": 0.0422, "steps": 98}, {"positions": [0.5838694791497636, 2.00604371592779, -1.066588497085402, 1.9828720080185096e-07, 0.7186069177891106, 0.5838693628925563], "gripper_width_m": 0.0422, "steps": 82}, {"positions": [0.5838643292668783, 2.0060479226216583, -1.0665982501362532, 1.3841162643505765e-06, 0.718612965573447, 0.7802125487396984], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5838584621701103, 2.0060449539313123, -1.0665909966302531, 2.5720569262826457e-06, 0.7186081662119644, 0.976555016207049], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5838528707435959, 2.0060399787600325, -1.0665788367042548, 3.4573839701912586e-06, 0.7186001205774852, 1.1728980302229124], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5838198902798233, 2.0060272058352995, -1.0665473527030183, 6.207844691402155e-06, 0.7185771067526225, 1.3692110978781444], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5837772227480122, 2.006001016303961, -1.066490200893205, 1.6583218060339452e-06, 0.7185351430704991, 1.5655202514115374], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5837371471972018, 2.005962029041404, -1.0664105504029806, -1.2828714885582473e-05, 0.7184766201891468, 1.7618404718637406], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5838671677747541, 2.0060464904334507, -1.0665941234656666, 1.7553465469079092e-07, 0.7186100843600107, 1.9583136807489183], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5838647134253349, 2.0060424771735015, -1.066584094309262, -1.81217891312359e-06, 0.7186034913862156, 2.1546621035230222], "gripper_width_m": 0.0422, "steps": 79}, {"positions": [0.5838703130963414, 2.031210248230434, -1.0581353383940582, 5.276694963693856e-08, 0.685000589230268, 2.1546666516869126], "gripper_width_m": 0.0422, "steps": 14}, {"positions": [0.6321964285746479, 2.1714832302196654, -1.330198348958692, 1.0787925885297255e-07, 0.8167687030226003, 2.202992648077409], "gripper_width_m": 0.0422, "steps": 109}, {"positions": [0.6576066953191738, 2.2768240758913505, -1.5392011003261434, 3.8525644697164644e-08, 0.9204394839261935, 2.2284030526242216], "gripper_width_m": 0.0422, "steps": 84}, {"positions": [0.6790249651700818, 2.3984877213383657, -1.7841783528761703, 3.2096060343858297e-08, 1.0437518245640565, 2.2498213337346264], "gripper_width_m": 0.0422, "steps": 98}, {"positions": [0.6885144095271486, 2.4696989781328704, -1.9290977829363856, 2.654943654664526e-08, 1.1174576769933195, 2.2593107910634185], "gripper_width_m": 0.0422, "steps": 58}, {"positions": [0.6973074546980692, 2.553102926873452, -2.1001275145394422, 2.0164854305973733e-08, 1.2050758031353668, 2.2681038697108233], "gripper_width_m": 0.0422, "steps": 69}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.0422, "steps": 87}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.0422, "steps": 120}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.0422, "steps": 24}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.0437, "steps": 7}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.0437, "steps": 96}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.0737, "steps": 120}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.08, "steps": 26}, {"positions": [0.6973075832879314, 2.7646532262962635, -2.096004754881934, 3.6588562768597025e-08, 0.9894135119988144, 2.2681039436869654], "gripper_width_m": 0.08, "steps": 120}, {"positions": [0.6973075840719497, 2.553386454812988, -2.100735033736921, 3.273840201692754e-08, 1.2054101830049297, 2.2681039528669342], "gripper_width_m": 0.08, "steps": 87}]
BOTTLE_ARM = "left"

ARM = "right"
APPROACH = [{"positions": [0.03486531223105153, 2.3617278309653664, -1.570072321443826, 1.0327003296206049e-05, 0.878996122950887, -1.5359326039386358], "gripper_width_m": 0.08, "steps": 43}]
DESCEND = [{"positions": [0.03486531072571333, 2.501739258950877, -1.573932939726305, 1.1757988864099242e-05, 0.742841784743163, -1.5359346779742162], "gripper_width_m": 0.08, "steps": 43}]
ROTATE = [{"positions": [0.03499801106069836, 2.5017661050344273, -1.5739683659487693, -0.00031625109118619654, 0.7428490840258706, -1.5530106551031249], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035113957529855515, 2.5017632859422325, -1.573961621831545, -0.0006387595875525014, 0.7428397584816269, -1.5701090796274055], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03522979868539029, 2.501757595167089, -1.5739481809681737, -0.0009610812434790539, 0.7428228306575547, -1.5872077453199651], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03534553760311581, 2.5017495474096885, -1.5739291828580746, -0.001283139401286045, 0.7427989746835869, -1.6043066987473926], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03546113986422968, 2.501739161938573, -1.573904671599355, -0.0016048452207942203, 0.7427682206488616, -1.6214060368681253], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035576570952087584, 2.501726442562494, -1.5738746560655252, -0.0019261098702502912, 0.7427305783454988, -1.6385058567734954], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03569179639595773, 2.50171139327461, -1.57383914558968, -0.0022468446009818797, 0.7426860588327949, -1.6556062554710944], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035806781782791626, 2.501694018778378, -1.573798151165751, -0.0025669607653051765, 0.7426346751629276, -1.6727073298640094], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.035921492766954714, 2.5016743245037514, -1.5737516854855556, -0.0028863698335453896, 0.7425764424020947, -1.6898091767330965], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03603589507988046, 2.501652316605953, -1.5736997629360352, -0.00320498341106814, 0.742511377627369, -1.7069118927192901], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03614995453970503, 2.501628001963422, -1.5736423995946047, -0.00352271325534646, 0.7424394999222047, -1.7240155743058674], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.0362636370608844, 2.501601388175492, -1.5735796132239064, -0.0038394712930679455, 0.742360830371392, -1.741120317800649], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.036376908663793346, 2.5015724835598285, -1.5735114232660152, -0.004155169637286324, 0.7422753920554787, -1.7582262193181366], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03648973548429997, 2.501541297149624, -1.5734378508360933, -0.004469720604621812, 0.7421832100446565, -1.7753333747615785], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.0366020837833178, 2.501507838690556, -1.5733589187155, -0.004783036732514293, 0.7420843113921176, -1.7924418798049575], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.036713919956331706, 2.501472118637498, -1.573274651344359, -0.005095030796533251, 0.7419787251268876, -1.8095518298748954], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03682521054289562, 2.5014341481510027, -1.5731850748135872, -0.0054056158277486395, 0.7418664822461244, -1.8266633201324678], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03693592223609979, 2.50139393909354, -1.573090216856387, -0.0057147051301663365, 0.741747615706897, -1.8437764454549253], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037046021892007286, 2.501351504025501, -1.5729901068392005, -0.006022212298232038, 0.7416221604174351, -1.8608913004173113], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037155476539055085, 2.501306856200979, -1.5728847757521442, -0.006328051234407169, 0.7414901532278583, -1.8780079792739783], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03726425338741969, 2.5012600095633086, -1.57277425619891, -0.006632136166820374, 0.7413516329203836, -1.895126575939989], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03737231983834358, 2.5012109787403802, -1.5726585823861492, -0.006934381666997876, 0.7412066401990146, -1.9122471839724038], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037479643493423705, 2.5011597790397224, -1.5725377901123336, -0.0072347026676759865, 0.7410552176787122, -1.9293698965514476], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.037586192163855024, 2.501106426443371, -1.5724119167561128, -0.007533014480698904, 0.7408974098740504, -1.9464948064615502], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03769193387963019, 2.501050937602502, -1.5722810012641546, -0.007829232815004717, 0.7407332631873564, -1.9636220060722596], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03779683689869426, 2.5009933298318505, -1.572145084138485, -0.008123273794702297, 0.7405628258963469, -1.9807515873190178], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03790086971604975, 2.5009336211039144, -1.5720042074233334, -0.008415053977241826, 0.7403861481412456, -1.9978836416838026], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.038004001072809636, 2.5008718300429327, -1.5718584146914778, -0.00870449037168143, 0.7402032819114022, -2.0150182601756272], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.0381061999652005, 2.500807975918661, -1.571707751030108, -0.0089915004570519, 0.7400142810314054, -2.032155533310894], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}, {"positions": [0.03820743565350759, 2.500742078639933, -1.5715522630262035, -0.009276002200822019, 0.7398192011466913, -2.049295551093603], "dtheta_deg": 1.0, "steps": 84, "seconds": 0.35}]
RELEASE = [{"positions": [0.03820743565350759, 2.500742078639933, -1.5715522630262035, -0.009276002200822019, 0.7398192011466913, -2.049295551093603], "gripper_width_m": 0.06, "steps": 120}, {"positions": [0.03820743565350759, 2.500742078639933, -1.5715522630262035, -0.009276002200822019, 0.7398192011466913, -2.049295551093603], "gripper_width_m": 0.08, "steps": 120}]
RETRACT = [{"positions": [0.038189824357245196, 2.2635641439170313, -1.6047629321835908, -0.00737912972985145, 1.0101981018169262, -2.0522426109615357], "gripper_width_m": 0.08, "steps": 82}]

GRASP_Z_M = 0.84
GRASP_XY_TOL_M = 0.03
GRASP_Z_TOL_M = 0.03
RPM_TARGET = 145.0
CLOSE_STEP = 0.030
CLOSE_STEPS = 120
MIN_WIDTH = 0.006
STALL_SEGMENTS = 5
MAX_REGRIPS = 1


def _one(arm, action, width=None):
    return {
        "arms": {arm: {"positions": action["positions"],
                        "gripper_width_m": action.get("gripper_width_m", width)}},
        "steps": int(action["steps"]),
    }


class Policy:
    def reset(self, instruction):
        self.task = instruction.get("task_id")
        self.robot = instruction.get("robot_profile")
        arms = instruction.get("arms", {})
        self.mode = None
        if self.robot == "dual_piper" and self.task == "bottle_transfer" and "left" in arms:
            self.mode = "bottle"
        elif self.robot == "dual_piper" and self.task == "stirrer_knob" and "right" in arms:
            self.mode = "stirrer"
        self.index = 0
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

    # -- bottle replay ---------------------------------------------------
    def _bottle(self):
        if self.index >= len(BOTTLE_ACTIONS):
            return {"finish": True}
        item = BOTTLE_ACTIONS[self.index]
        self.index += 1
        return {"arms": {BOTTLE_ARM: {"positions": item["positions"],
                                       "gripper_width_m": item["gripper_width_m"]}},
                "steps": int(item["steps"])}

    # -- stirrer skill ---------------------------------------------------
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

    def _start_release(self):
        self.phase = "release"
        self.release_i = 0
        return _one(ARM, RELEASE[0])

    def _stirrer(self, obs):
        if self.wait > 0:
            self.wait -= 1
            return {"arms": {}, "steps": 2}
        instr = obs.get("instruments", {}).get("stirrer", {}) or {}
        rpm = instr.get("setpoint_rpm") or 0.0
        state = obs["proprioception"][ARM]
        tcp = state["tcp_position_m"]
        width = state["gripper_width_m"]

        if self.phase == "approach":
            self.phase = "descend"
            return _one(ARM, APPROACH[0])
        if self.phase == "descend":
            self.phase = "verify"
            return _one(ARM, DESCEND[0])
        if self.phase == "verify":
            dx = tcp[0] - 0.30
            dy = tcp[1] + 0.08
            dz = tcp[2] - GRASP_Z_M
            ok = abs(dz) <= GRASP_Z_TOL_M and (dx * dx + dy * dy) ** 0.5 <= GRASP_XY_TOL_M
            if not ok and self.retries < 2:
                self.retries += 1
                self.wait = 3
                return _one(ARM, DESCEND[0])
            if not ok:
                self.phase = "abort"
                return _one(ARM, RETRACT[0])
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
                return _one(ARM, RETRACT[0])
            action = RELEASE[self.release_i]
            self.release_i += 1
            return _one(ARM, action)
        if self.phase in ("retract", "abort"):
            self.phase = "done"
            return _one(ARM, RETRACT[0])
        return {"finish": True}

    def act(self, observation):
        if self.mode == "bottle":
            return self._bottle()
        if self.mode == "stirrer":
            return self._stirrer(observation)
        return {"finish": True}
