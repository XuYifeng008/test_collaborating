# 自主实验九题（lab-nine-20261024-v1）参评记录 · 策略实现 / 冻结产物 / 正式入口核验

> 执行时间：2026-10-24 17:00–18:10（Asia/Shanghai）
> 执行方式：Agent 按公开包 `AGENT_GUIDE.md` / `SUBMISSION.md` / `docs/SDK.md` / `docs/TASKS.md` / `docs/SCORING.md` / `docs/运行档.md` 自动完成
> 结论口径：**本地实现与冻结产物真实完成；九题正式提交入口本轮不存在，未产生 Attempt ID、未产生 36 槽结果或最终分——不伪造任何分数。**
> 证据根目录：`deliverables/2026-10-24-nine-task/`（本报告同目录）

---

## 0. 结论先行

1. **身份确认**：本轮开放两机器人赛道 `franka`（臂 `arm`，7 关节）与 `piper-dual`（`left`/`right`，各 6 关节），二者分别计分；唯一开放模型为 `rynnbrain-1.1-2b-local`（`Alibaba-DAMO-Academy/RynnBrain1.1-2B`@`36069aa8…`，权重 SHA256 `2819d84441c27…`）；运行档 `lab-nine-image-model-v1`（NumPy 1.26.4 / Pillow 11.3.0 / opencv-python-headless 4.11.0.86）。规则身份 `lab-nine-20261024-v1`，九题 × 4 重复 = 36 槽、九题等权。
2. 已实现一份**仅使用公开观测**的 `lab-policy-v2` 策略（协议、公开运动学 FK/IK、公开 RGB 感知、九题状态机、C07 去皮/定量流程、两波频率与 finish 语义均按合同读取），并用官方 `lab_sdk.packaging` **冻结**成两个赛道的 `outputs`（各 `canonical.zip` + `wave1.zip` + `wave2.zip` + `package-receipt.json`），逐字节确定性、全部限额与回执哈希复核通过。
3. 本地真实证据：公开包身份/合同核验 **930 项检查、0 项不符**；4 份真实公开指令/观测样例经官方 `Adapter` 与策略回归全部通过（确定性）；冻结派生包的 wrapper 运行时身份绑定/机器人绑定/协议合法性 **8 项检查全部通过**；C07 去皮-定量状态机用「运动学 mock + 合成感知 + 合成天平回执」跑通（**明确标注非物理**）。
4. **正式提交判定（关键）**：本轮公开包与平台当前状态都**没有** `lab-nine-20261024-v1` 的可用正式入口：`release.json` 明确 `playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`、`live_nine_task_service_deployed=false`；`contracts/rules-v1.json` 的 `platform.challenge_ids=null`；`contracts/configuration-template.json` 两个后端 `url=null`、`deployment_qualified=false`；唯一可达 HTTP 服务实测是旧 **五题** 联调服务（`benchmark_id=lab-agent-v0.4-five-tasks-dev`，`/v1/tasks` 缺 `nine_task_binding`/`runtime_profile_sha256`/`configuration_sha256`/`runtime_capabilities`，`/v1/challenges`、`/v1/attempts` 均 404）；平台官方 `playground` CLI 虽已认证（`api_base=https://play.bohrium.com/api`），但 **6932 个可见 Challenge 中无本题、工作区无本题 Challenge ID**，无法创建正确 Attempt。
5. 因此：**未执行任何 POST/上传/创建评测**（避免产生错误评测记录）；**没有 Attempt ID 可保存**，也没有 `state=scored`、`scoreIsFinal=true`、`planned_count=scored_count=36` 可查询——这些字段本轮客观不存在。把上传成功或空策略 0 分当作任务成功是明确禁止的，本报告不这样做。
6. 正式入口要可用，还差：平台 Challenge/Attempt 接入（Host 服务 ↔ Playground 转发/回写，M5）、`deployment_qualified=true` 的部署配置与两后端真实 URL/资格 ID、九题新运行档的双后端资格与 36 槽独立归档。见 §6。
7. 本地实现**不代表物理可用**：公开包不含九题仿真器/裁判/资格服务，策略从未在本轮九题物理环境中执行过，本报告不声明任何任务成功、分数或排名。

---

## 1. 本轮开放身份与规则（对照 `release.json` / `contracts/` 实测）

| 项 | 值（实测/合同） |
|---|---|
| 规则身份 | `lab-nine-20261024-v1`，rules version 1.0.0，editorial_revision=3 |
| 规则规范 JSON SHA256 | `e65b8edb7afc1d2ee901e2b5589f372028def43c319e66bb4852e7754c8dbc11`（与 release 一致） |
| 运行档 | `lab-nine-image-model-v1`，规范 JSON SHA256 `b32b478e6b0051e53fb774fc3b52b666352c8c427d3e6ec3e1994d7b41341639`（与 release 一致） |
| 配置模板 | `lab-nine-local-preview-20261024-v1`，规范 JSON SHA256 `0e50177954035a578741140edf0bd68a7ac254e807b739fff3a89176e12894d2`（与 release 一致）；**仅本地预览，url=null、deployment_qualified=false** |
| 机器人 | `franka`：臂 `['arm']`/7 关节；`piper-dual`：`['left','right']`/各 6 关节；wave2 原生 `arm`→统一 `left` |
| 夹爪范围 | wave1：franka/piper 均 [0,0.08] m；wave2：franka [0,0.08] m、piper [0,0.1] m（每回合以指令为准） |
| 物理频率 | 前五题 240 Hz（`step_seconds=1/240`）、后四题 120 Hz（`step_seconds=1/120`） |
| finish | wave1：`hold current targets for 720 real physics steps, then end`（+720 步）；wave2：`extra_physics_steps=0`（不加步） |
| 槽位/计分 | 9 题 × 4 重复 = 36 槽；`100 * Σ(每题成功数/4) / 9`；中间不舍入、显示 6 位；同分并列 |
| 预算 | wave1：CPU 120 s / 墙钟 600 s；wave2：CPU 120 s / 墙钟 3600 s、每回合 1200 s×120 Hz=144000 步、10000 次唯一变更请求（observation 除外） |
| 模型 | 仅 `rynnbrain-1.1-2b-local`；模型注册表 SHA `9d60ca7505d1…`、wheel 锁 SHA `dd495064d834…` 与运行档互绑 |
| 平台状态 | `playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`、`challenge_ids=null` |
| release 补充 | `live_nine_task_service_deployed=false`、`new_runtime_native_full36_verified=false`、`external_model_api_qualified=false` |

公开包身份核验（`evidence/contracts/`）：`PUBLIC-MANIFEST.json` 覆盖 33 个文件，逐文件 bytes+sha256 **33/33 匹配**；release/规则/运行档/配置模板/SDK source/模型注册表/wheel 锁全部一致；930 项检查、**0 项不符**、15 项记录。

---

## 2. 策略实现（`src/my-policy/`，6 个文件，源码 66,335 B）

| 文件 | 作用 |
|---|---|
| `submission.json` | `lab-submission/v2` / `lab-policy-v2`，`submission_id=nine-task-policy-001`，entrypoint=`policy.py` |
| `policy.py` | 协议解析、预算、动作白名单校验、两波 finish 语义、C07 仪器动作、感知 hook |
| `kinematics.py` | 只用公开 `robot_kinematics` 的 FK + 阻尼最小二乘 IK；TCP 帧常数从首个公开 `proprioception` 校准；关节限幅/限速 |
| `vision.py` | 只解码公开 PNG 的 RGB 感知（颜色框、瓶盖、亮/暗目标、量筒液面），纯 NumPy/Pillow（cv2 可选） |
| `skills.py` | 九个任务的状态机、运动原语（视觉伺服/抓取停滞检测/倾角/等待稳定） |
| `README.md` | 策略说明、模型声明、C07 流程、验证边界 |

### 2.1 只使用公开观测（逐项）

- 关节顺序/数量：只读 `instruction.arms[arm].joint_names`（wave1 为 `arm_joint_names`），不按另一机器人维度写死；piper 第二波原生 `arm`→统一 `left` 由 SDK `Adapter` 完成，策略只认统一键。
- 图像：只用 `observation['images']` 中实际下发的相机 payload；相机 ID 不假设固定（按 `overhead/global/basket/tube/…` 名字做优先级匹配）；`lab_sdk.images` 的 16 MiB/16M 像素上限同样遵守。
- 频率/步数：只读 `instruction.physics.step_seconds`/`frequency_hz`；动作 `steps` 恒为 1–120 整数；不把“秒数×240/120”写死成步数。
- 结束行为：`finish.extra_physics_steps` 为 720 时策略只发精确 `{"finish": true}`（后端保持目标推进 720 步）；为 0 时策略先自行用保持动作推进 ≥1.25 s 物理步（120 Hz ≥150 步）再 finish。
- 预算：wave1 读观测里的 `budget.remaining_*` 并预留 finish；wave2 按公开上限（144000 步 / 10000 次变更调用）自行累计。
- C07 仪器：`competition_balance.read/tare` 只作为**独立动作**返回，绝不与 `arms/steps` 混在同一动作。

### 2.2 C07 去皮流程（状态机实测口径）

1. 空接收杯上秤盘 → 释放 → 同臂撤离（≥30 mm 以上量级的移动），等待 ≥1.4 s 物理步；
2. `read`：只有 `ok is True` 且（`stable is True` 或 `status=="STABLE"`）才算有效，连续 **≥2 次**有效 stable 读后才 `tare`；
3. `tare` **只发一次**；有效去皮后不再改变去皮版本；若回执无效/缺字段 → 不把旧质量当有效、不重复 tare，走安全收尾；
4. 持源杯、倾角 ≥40° 出液，每 0.5 s 物理步 `read` 净质量，达到 10±0.5 g 回正；
5. 源杯回位释放撤离、终态保持 ≥1 s 并复读确认；`instrument` 与机械臂动作分开。
   （该流程用运动学 mock + 合成回执验证：tare 恰 1 次、首 tare 在 496 步、19 次 read、净质量到 10.4 g、finish 于 2418 步——**非物理**，见 §4.3。）

### 2.3 诚实标注

策略中**没有任何**“自报成功”字段或捷径：不读私有物体位姿/接触真值/裁判状态，不直接改物体、液量或仪器真值；感知不可用（`None`）时一律安全收尾（保持 + finish），不猜测、不盲称成功。策略不发起模型推理（模型身份由运行档/注册表绑定，见 `README.md`）。

---

## 3. 冻结产物 `outputs/`（官方 `lab_sdk.packaging` 生成）

冻结命令（两赛道分别执行，输出目录为新建且位于源目录之外）：

```text
python -m lab_sdk.packaging deliverables/2026-10-24-nine-task/src/my-policy \
  --output deliverables/2026-10-24-nine-task/outputs[ -piper-dual] \
  --robot franka|piper-dual \
  --runtime-profile-sha256 b32b478e6b0051e53fb774fc3b52b666352c8c427d3e6ec3e1994d7b41341639 \
  --configuration-sha256 0e50177954035a578741140edf0bd68a7ac254e807b739fff3a89176e12894d2
```

| 产物 | franka（主提交候选） | piper-dual |
|---|---|---|
| `canonical_source_sha256` | `b6a78c5adfc3e5e891b1f7bcd5d6aba807e80be67f482842c2c0f663bf7246f4` | 同左（同一源码） |
| `canonical.zip` | 67,242 B / `2735bb06a066f8db79d2f2fbe16d2bea521ee6fa6302ef5e87cc4bce03deb26a` | 同字节 |
| `wave1.zip` | 89,327 B / `f4e43152182b4800fea7d52150e0933edc2759d07f6f019bc4886f5d01522ee4` | 89,335 B / `fc04a286b6cead3bbdbae1271cc98efbde930580703aa2de1c2daba4dbfc2d23` |
| `wave2.zip` | 89,327 B / `92323c48abbd32c5161f918cbbb7bd2add3712ba182ee9eb90ef0f9cfc288a35` | 89,335 B / `d56052c172ad368881be67c0cf6c901e6cc7a44284b4cf2035a78c6330cb2fdb` |
| `package-receipt.json` | 2,613 B / `8bb7058a02a439976c17344f70b20b93c530717ecae091c9198fed4085d32e0c` | 2,617 B / `64b1b9c91a6bbd8fb921d0d4a52238cfda1ebbddb2492e29385b1ec381ea48d1` |

复验（`evidence/packaging/freeze-summary.json`）：
- 回执与 source/ZIP/成员 SHA 逐项一致（两赛道 `problems=[]`）；
- 同一输入二次打包到新目录，四个文件逐字节相同（两赛道 `deterministic=true`）；
- 限额满足：canonical 6 文件 / 66,636 B；每个 ZIP 14 文件 / 89 KB；解包、单文件、文件数远超上限余量；
- 两个赛道 `canonical.zip` 字节完全相同（同一冻结源码），差异只在派生包 manifest 的 robot/arm 包装。
- 派生包 wrapper 身份绑定（`evidence/wrapper/wrapper-roundtrip.json`）：缺 runtime_context / 缺模型 API / 缺图像依赖 / 错运行档 SHA 均被 `ContractError` 拒绝；正确绑定时 wave1 franka 与 wave2 piper 均只输出合法 v1 动作并 finish；franka 包拒绝 piper 指令。

> 说明：按 `SUBMISSION.md`，正式提交需要“整个 outputs 中的四个文件”。本目录 `outputs/`（franka）与 `outputs-piper-dual/`（双 PiPER）分别就绪；由于正式入口不存在（§5），**没有上传任何产物**。

---

## 4. 真实开发与测试记录

### 4.1 公开包身份与合同核验（独立队友执行，只读、未联网）

`evidence/contracts/contract-verification.md` / `.json` / `verify_contracts.py`（可复现）：
- 930 项检查：通过 915、**问题 0**、记录 15；
- PUBLIC-MANIFEST 33/33 文件 bytes+sha256 匹配；
- release ↔ rules/runtime-profile/configuration/SDK-source/model-registry/wheels 全部一致；
- 4 份真实 fixtures × Adapter：wave1 franka、wave1 piper、wave2 piper C07、wave2 franka C02 全部通过（合计 477 项内部检查，动作合法/非法矩阵含关节数、steps 越界、非有限数、越限、未知臂/字段、finish 精确 dict、instrument 仅 wave2 C07 等）。
- 如实记录的限制：release 的 runtime 归档/测试日志未随公开包发布无法独立复核；fixtures 的原始 SHA 无原件无法重算；仅 3 题有真实协议样例。

### 4.2 策略 × 真实样例回归（Lead + 测试夹具）

- 4 个真实 fixture 经官方 `Adapter` 驱动策略（无图像 → 感知不可用 → **安全收尾**）：全部 `finish`、动作全部通过官方 `Adapter.action()` 校验、预算内、两次运行动作序列逐字节一致（确定性）。
  - Lead smoke（策略自身发出的动作）：wave1 franka/piper 各 32 calls / 260 steps（`step_seconds=1/240`、`finish.extra_physics_steps=720`、关节 7/6+6）；wave2 piper C07 54 calls / 1010 steps（含 finish 前 150 步保持 = 1.25 s，`1/120`、`extra=0`）；wave2 franka C02 34 calls / 410 steps。
  - 测试夹具（按后端 finish 语义记账）：wave1 franka 26 calls / 930 steps（含后端追加 720 步）、piper 32 / 980；wave2 C02 23 / 314、C07 31 / 396（二者均含 finish 前 150 步保持）。
- 冻结派生包 wrapper 往返：见 §3 最后一条（8/8 通过）。
- 公开图片解码与 RGB 感知函数在公开 `examples/sdk-public-image.json` 上冒烟（`evidence/perception/`、`evidence/logs/perception-smoke.log`）：PNG 解码为 800×600×3 RGB，颜色框检测到 green/blue，白帽 blobs=4，亮/暗目标与量筒液面（fill≈0.57）均可计算。只解码公开 PNG，不含私有数据/网络。
- **独立测试夹具**（`tests/`，队友构建；运动学 mock + 合成感知/天平桩仅用于状态机，不冒充物理）最终结果：**17 个测试 17 PASS / 0 FAIL / 0 ERROR**（34.59 s），见 `tests/TEST_RESULTS.md`、`tests/test-results.json`。覆盖：4 份真实样例协议回归、频率/关节顺序/finish 语义、14 份协议合成用例 smoke、驱动器 11 个故意违规 stub 全部拒绝、C07 nominal/异常/持续异常四组去皮状态机。
  - 该套件在开发中发现并驱动修复了一个真实缺陷（已复测）：wave2 `finish` 前保持步数曾被截断为 120 步（1.0 s < 1.2 s），修复后 real:C07/real:C02 均 `terminal_hold_steps=150`（1.25 s），两次运行 action digest 一致。
  - C07 nominal（合成感知+脚本化天平桩）：150 calls / 1848 steps；tare 尝试 1 次且有效 1 次；tare 前有 168 步 hold + 2 次有效 stable read；tare 后 9 次 read，净质量 4.53→10.10 g 均在容差；最终 10.10 g；无二次 tare；instrument 从不与 arms 混合同一动作；finish 前保持 450 步；两次运行 digest 相同。

### 4.3 C07 去皮-定量状态机（Lead dev 记录，非物理）

`evidence/logs/`（运动学 mock：命令即测量、夹爪在 <0.055 m 处模拟物体停滞、合成感知与合成天平回执；**不是仿真器/不是物理成绩**）：
- 有效 read → stable 计数 → 首次 `tare` 恰 1 次（step 496）→ 出液 → read 19 次 → 净质量 10.4 g → 回位释放 → 保持 → finish（step 2448，含 finish 前 150 步保持）。
- 异常回执路径（unstable/缺字段）不重复 tare、不把异常值当有效质量、不立即 finish 冒充完成（`tests/TEST_RESULTS.md` 中三组异常用例 PASS）。

---

## 5. 正式提交流程判定：本轮九题正式入口不存在

### 5.1 证据链（静态 + 网络非破坏性探测）

1. **公开包自身声明**（最高优先级）：`release.json` 第 42–46 行 `live_nine_task_service_deployed=false`、`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`；`contracts/rules-v1.json` 第 589–597 行 `platform.challenge_ids=null`；`contracts/configuration-template.json` 第 30–51 行两个后端 `url=null`、`deployment_qualified=false`；`docs/发布接入清单.md` 第 3 行“Playground 目前未配置…不重复索要 Challenge”。
2. **旧服务不是九题入口**（实测）：唯一可达 HTTPS 服务为 `inbox/lab-embodied-pilot-20261023/participant-kit/service.json` 的旧五题联调服务。`evidence/probes/` 只发 GET、未 POST：
   | 探测 | 结果 |
   |---|---|
   | `GET /health`（无鉴权） | 200 `lab-eval-pilot-health/v1` |
   | `GET /v1/tasks`（无鉴权 / Bearer） | 401 `UNAUTHORIZED` / 200，`schema=lab-eval-pilot-catalog/v1`，`benchmark_id=lab-agent-v0.4-five-tasks-dev`，5 题、`scopes={"full":20,"smoke":4}` |
   | `nine_task_binding` 等四字段 | **全部缺失**（false/false/false/false） |
   | `GET /v1/challenges`、`GET /v1/attempts`、`GET /v1/evaluations`（列表） | 全部 **404 NOT_FOUND** |
   | 同域 :8787/:8090/:8890 直连 | 无响应（该域名只经 443 反代到旧服务） |
   | catalog `native_qualification` | 新旧五题均为 `not_qualified_in_current_delivery`（当前交付未取得原生资格） |
   - 结论：该服务既没有九题的 Challenge/Attempt 概念，也没有九题新后端绑定字段，按 `docs/SUBMISSION.md` 第 65–69 行与 `docs/平台接口.md` 第 52–74 行**不能冒充**统一九题正式入口。
3. **平台官方 CLI 通道存在，但本题未上架**（只读核查，未 submit）：PATH 中存在官方 `playground` CLI 0.1.40（npm `@paper2arm/playground-cli`），`playground auth status` 显示**已认证**（`api_base=https://play.bohrium.com/api`）；但全量可见 Challenge **6932 个中没有任何本题九题具身实验题目**（强匹配 24 条经人工核对均为 `nine-gene`/`nine-point`/`manipulator` 等子串或无关化学题），且工作区没有任何本题 Challenge ID 配置（`C:\Users\86150\.playground\config.json` 不存在）。`playground submit` 会创建 Attempt（POST），**按约束未执行**。→ “有 CLI”≠“本题正式入口可用”：没有 Challenge ID 就无法创建正确的 Attempt。
4. **静态搜索**：工作区检索 `nine_task_binding`/`deployment_qualified=true`/Challenge/Attempt/正式 URL/CLI：`deployment_qualified=true` **0 命中**；`nine_task_binding` 只出现在文档/规则描述里，无已部署后端响应；`python -m organizer` 未安装（公开包不含组织者部署代码）；本机 8090/8787/8890 无监听；环境变量无平台注入。
5. **组织者侧当前状态佐证**（本机工作上下文，非公开包证据）：`work-context/maps/embodied-competition-hosting.md` 与 `map/embodied-competition-ledger.md` 记录“Playground 转发/回写（M5）”仍为 ❌、“Host 服务 ↔ Playground 转发协议未定/待平台确认”，与公开包 `competition_ready=false` 一致。

### 5.2 因此本轮能/不能做什么

| 用户要求 | 本轮实际 |
|---|---|
| 通过本题实际入口正式提交一次 | **无法执行**：官方 `playground` CLI 已认证，但本题 Challenge 未上架、无 Challenge ID（6932 个可见 Challenge 中无本题），无 ID 无法创建正确 Attempt；旧服务明确是五题开发联调且当前交付未资格，提交它属于“旧五题接口伪装九题正式评测”，被 `AGENT_GUIDE.md` 第 9 行与 `SUBMISSION.md` 第 65–69 行禁止。为避免制造错误评测记录，**未 POST、未上传、未创建任何 evaluation**（含未执行 `playground submit`）。 |
| 保存 Attempt ID | **没有**：不伪造。旧服务的 `eval-…` ID 不是九题 Attempt；本报告与证据目录中不含任何 Attempt/评测 ID/分数。 |
| 持续查询同一提交、核对 36 槽位及最终分 | **无法执行**：无提交可查。36 槽完整分的判据（`state=scored`、`scoreIsFinal=true`、`planned_count=scored_count=36`）本轮客观无法取得；`scoreIsFinal=true` 只在本地聚合语义下才可能，不能当正式分。 |
| 上传成功≠成功、空策略 0 分≠成功 | 严格遵守：本轮既没有上传成功，也没有任何 0 分/满分记录；不把“无入口”包装成“已提交”。 |

### 5.3 正式提交可用后需要什么（可直接照做的验收清单）

1. 平台侧：Challenge ID + 提交入口（Trusted Attempt 产物接入）+ 官方回写 schema/鉴权/幂等 + 榜单读回（`docs/发布接入清单.md` 交付栏）。
2. 组织者侧：新配置 `deployment_qualified=true`，两后端真实 URL/`benchmark_id`/`backend_source_sha256`/`asset_source_sha256`/`execution_profile_sha256`/`qualification_id`；`GET /v1/tasks` 返回 `nine_task_binding` 与 `runtime_profile_sha256`/`configuration_sha256`/`runtime_capabilities`。
3. 运行档侧：安装并核验本版 image/model runtime，绑定唯一模型权重（SHA `2819d844…`）与项目 `runtime_manifest_sha256=67014954…`。
4. 选手动作：同一冻结 canonical 源码按 `--robot franka|piper-dual` 重新打包（本目录已有两套）；平台 `register → plan → preflight → submit → wait → result`；保存 Attempt ID 与两个 child evaluation ID；只认 `state=scored`、`scoreIsFinal=true`、`scored_count=planned_count=36` 且平台回写=物理分一致。
5. 基础设施缺失/身份不一致槽位为 `null`，不剔除分母；策略失败不重跑。

---

## 6. 提交与评测时遇到的问题归纳（含复现/影响/处理）

| # | 类别 | 现象 | 原因 | 处理/建议 | 证据 |
|---|---|---|---|---|---|
| 1 ★ | 正式入口 | 没有本题九题的 Challenge ID / 提交入口，无法正式提交 | 本版 `competition_ready=false`、`playground_integrated=false`、`live_nine_task_service_deployed=false`；平台转发协议（M5）未落地；官方 `playground` CLI 虽已认证，但本题 Challenge 未上架（6932 个可见 Challenge 中无本题）、工作区无 Challenge ID | 不伪造；把本页 §5 作为阻塞证据报给组织者/平台；拿到 Challenge ID 后可执行 `playground submit --challenge-id <ID> --outputs <dir> --trace <session.jsonl>` 并按 §5.3 核对 36 槽；在此之前不 POST | `release.json`、`contracts/rules-v1.json`、`configuration-template.json`、`evidence/probes/`（含 `raw/cli-playground-entry-evidence.json`） |
| 2 ★ | 旧服务 | 唯一可达服务是旧五题联调（v0.4），且 `native_qualification=not_qualified_in_current_delivery` | 旧服务无九题绑定字段/无 Challenge/Attempt 路由；本交付未取得五题原生资格 | 只做非破坏性 GET 取证；**未 POST**；不得用其 `eval-…` 冒充九题 Attempt | `evidence/probes/probe-report.md` |
| 3 ★ | 可评测性 | 公开包不含九题仿真器/裁判/资格服务，策略无法做物理闭环验证 | 公开包定位为编写/检查/冻结选手策略；物理资格在组织者侧 | 只用真实 public fixtures 做协议级回归 + 运动学 mock 做状态机测试，全程标注“非物理”；不声明任务成功 | §4、`tests/` |
| 4 ★ | 公开数据 | 4 份公开样例无图像；只有 3/9 题有真实协议样例 | 样例投影移除了平台身份与图像 payload | 策略对无图像输入安全收尾；其余 6 题只用合成协议用例（明确标注 synthetic） | `contracts/contract-verification.md` §6、`tests/` |
| 5 | 依赖完整性 | 本地 Pillow 11.2.1 ≠ 运行档 11.3.0；本地无 cv2；未加载模型 | 桌面开发环境非正式 Linux 运行档 | 策略只依赖 numpy/PIL，cv2 可选；Pillow 版本差异只影响本地开发，正式身份以运行档 wheel 锁为准；不宣称本地测试=运行档资格 | §1、`src/my-policy/README.md` |
| 6 | 打包工具 | `read_source` 因 `__pycache__` 拒绝打包 | 开发时在源码目录 import 产生了缓存 | 打包前清理 `__pycache__/*.pyc`；打包工具还会拒绝 `.git/.env/链接/特殊文件` | `evidence/packaging/` |
| 7 | 打包工具 | 输出目录必须“新建”，重复打包报 `FileExistsError` | 工具用 `mkdir(exist_ok=False)` | 每次冻结用新目录；确定性复验用临时目录；旧产物保留 | 同上 |
| 8 | 冻结身份 | 自填 SHA、或沿用旧五题/四题配置会导致包被拒 | 必须用本版 `runtime-profile`/配置模板的规范 JSON SHA（发布值 `b32b47…`/`0e5017…`） | 用 SUBMISSION.md 的规范 JSON 算法计算并和 release.json 对账后再打包 | §3、`freeze-summary.json` |
| 9 | wrapper 身份 | 派生包在缺 runtime_context/缺模型/缺图像依赖时 `ContractError` | `lab_sdk.policy.require_runtime` 的设计 | 这是预期行为；不要把它当“工具坏了”，也不要把裸 v1 包送旧服务 | §3、`evidence/wrapper/` |
| 10 | C07 去皮 | 早期状态机在“未稳定就 tare”/“重复 tare”上会失败 | 规则：首次有效去皮后再次改变去皮版本会使回合失败 | 连续 ≥2 次有效 stable read 后才 tare 一次；异常回执不重试 tare，走安全收尾 | §2.2、`evidence/logs/` |
| 11 | C07 字段 | 真实天平回执字段集未公开 | 文档只保证“正常 UniLabOS 天平驱动/read 回执” | 策略宽松解析 `ok/stable/status/net_mass_g/tare_version`，缺失/不稳定一律不当有效质量 | `skills.py:parse_balance` |
| 12 | 动作合同 | 关节数/steps/夹爪开度/非有限数/arm+instrument 混合都会被拒 | SDK 需要严格动作 | 策略输出前统一白名单校验 + clip；instrument 单独动作 | `policy.py:_validate_action` |
| 13 | 频率 | 把两波按同一固定步数写死会错 | 前五题 240 Hz、后四题 120 Hz，finish 语义不同 | 只读 `instruction.physics.step_seconds`/`finish.extra_physics_steps` | §2.1 |
| 14 | Windows/TLS | PowerShell `Invoke-WebRequest`/`curl.exe` 对 Bohrium 报 schannel `SEC_E_NO_CREDENTIALS` | 本机 curl schannel 凭据链问题 | 改用 Python `urllib`（默认证书校验）完成探测；报告记录排查过程 | `evidence/probes/probe-report.md` |
| 15 | 旧服务时区 | `accept_until/expires_at` 是 UTC，容易误判 | 回执用 UTC | 按 UTC+8 换算；本轮窗口 2026-10-26 12:00/18:20 但**不是**九题赛期 | probe raw meta |
| 16 | 身份误用 | `submission_id`、`package_id`、`Attempt ID`、`eval-…` 是四种不同身份 | 不同层由不同系统签发 | 报告中严格区分；本轮四者均不伪造 | §5.2 |
| 17 | 策略缺陷（已修复） | wave2 `finish` 前保持步被截断：total=150 只发出 120 步（1.0 s）就 finish | `_finish_tick` 在发出最后一段前就返回了 finish，剩余 30 步被吞 | 改为“先发完剩余保持步、最后一步才 finish”；独立夹具复测 terminal_hold=150 步（1.25 s），17/17 PASS | `tests/TEST_RESULTS.md` 过程性缺陷记录、`policy.py:_finish_tick` |

---

## 7. 复现方式

```powershell
# 0) 环境：Windows + D:\python\python310\python.exe（3.10.11, numpy 1.26.4, Pillow 11.2.1）
cd E:\dev\agents\lark-working

# 1) 公开包身份/合同核验（只读，930 项）
python deliverables\2026-10-24-nine-task\evidence\contracts\verify_contracts.py

# 2) 冻结两赛道产物（输出目录必须不存在）
python deliverables\2026-10-24-nine-task\evidence\packaging\freeze_outputs.py

# 3) 冻结派生包 wrapper 往返验证（8 项）
python deliverables\2026-10-24-nine-task\evidence\wrapper\wrapper_roundtrip.py

# 4) 官方测试夹具（队友构建的 tests/）
python deliverables\2026-10-24-nine-task\tests\run_tests.py

# 5) 正式入口非破坏性探测（只 GET、token 不落盘；含官方 playground CLI 只读核查）
python deliverables\2026-10-24-nine-task\evidence\probes\probe_entry.py

# 6) 公开 PNG 感知冒烟（只解码公开 examples/sdk-public-image.json）
python deliverables\2026-10-24-nine-task\evidence\perception\perception_smoke.py
```

## 8. 文件清单（本目录）

```text
deliverables/2026-10-24-nine-task/
├─ REPORT.md                          ← 本报告
├─ src/my-policy/                     ← 策略源码（6 文件，66,636 B）
├─ outputs/                           ← 官方冻结产物（franka：canonical/wave1/wave2/receipt）
├─ outputs-piper-dual/                ← 官方冻结产物（piper-dual）
├─ tests/                             ← 独立协议测试夹具与结果（TEST_RESULTS.md / test-results.json）
└─ evidence/
   ├─ contracts/                      ← 公开包身份/合同核验（930 项，0 不符）
   ├─ probes/                         ← 正式入口探测（只读 GET + playground CLI 只读核查，含原始响应+sha256）
   ├─ packaging/                      ← 冻结摘要、两赛道回执、确定性验证
   ├─ wrapper/                        ← 冻结派生包 wrapper 身份/协议往返
   ├─ perception/                     ← 公开 PNG 感知冒烟
   └─ logs/                           ← Lead 真实开发/测试日志
```

## 9. 边界声明

- 本报告是**参赛侧开发与提交链路记录**，不是官方成绩；本轮无官方评测、无 Attempt、无 36 槽结果、无最终分。
- 策略未在任何九题物理仿真/资格环境中执行过；运动学 mock、合成感知、合成天平回执均为**状态机/协议**验证，不构成物理成功证据，也不代表模型/策略能力。
- 报告中引用的公开包字段、SHA 与探测结果均可由本目录脚本复现；不含 token、平台密钥、私有裁判数据或未授权内容。
- `competition_ready=false` 解除前，任何“已提交/已得分”的表述都不成立。
