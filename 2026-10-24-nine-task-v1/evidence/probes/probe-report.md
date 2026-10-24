# 九题正式入口非破坏性探测报告（lab-nine-20261024-v1）

- 生成时间（UTC）：`2026-10-24T09:29:51.727Z`（本地 `2026-10-24T17:29:51+08:00`）
- 执行脚本：[`probe_entry.py`](probe_entry.py)（**只发送 HTTP GET**；无上传、无创建评测、无提交策略）
- token：只从 `inbox/colleague-test-01.token` 读入内存并放入 `Authorization: Bearer` 请求头，
  值不落任何文件（长度 43 字符，泄漏终检：**通过**）
- 输出目录：`deliverables/2026-10-24-nine-task/evidence/probes/`（raw 原始响应、summary、本报告）

## 0. 结论先行

**未发现 lab-nine-20261024-v1 的九题正式入口。正式提交不可执行、Attempt ID 无法在不伪造的前提下取得。**

- 静态搜索：没有本题的九题正式入口配置（无 `deployment_qualified=true` 的部署配置、无本题 Challenge ID、无正式提交地址、无平台凭据）。
- 平台 CLI 核查：PATH 中确实存在官方 `playground` CLI（@paper2arm/playground-cli，`Playground CLI 0.1.40`），`auth status` 显示**已认证**（`api_base=https://play.bohrium.com/api`）；但**本题 Challenge ID 未配置**，全量可见 Challenge（`6932` 个）中没有本题九题具身实验 Challenge，而 `playground submit` 会创建 Attempt（POST），按本任务约束**未执行**。
- 网络探测：旧包 `service.json` 声明的唯一评测后端是“五题邀请联调服务”，catalog 的 `benchmark_id` 与九题规则身份不一致，且**缺少九题新后端的全部绑定字段**（`nine_task_binding` / `runtime_profile_sha256` / `configuration_sha256` / `runtime_capabilities`），按合同不能当正式入口。
- 公开包自身声明：`challenge_ids=null`、`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`、`live_nine_task_service_deployed=false`，部署模板两个后端 `url=null` 且 `deployment_qualified=false`。
- 因此本次**没有产生任何 Attempt ID**；本目录所有文件都不含 Attempt ID / 评测 ID / 分数（也不允许出现伪造值）。

## 1. 探测方法与安全约束

| 项 | 内容 |
|---|---|
| HTTP 方法 | 仅 `GET`（脚本内 `METHOD = "GET"` 是唯一方法常量；`urlopen` 的 `data=None`） |
| 是否创建对象 | 否。未 POST、未上传 ZIP、未创建 evaluation/Attempt、未提交策略 |
| token 使用 | 仅 `inbox/colleague-test-01.token` → `Authorization: Bearer` 请求头；URL 中无 token；输出前中后各做一次 token 泄漏扫描 |
| token 输出 | 不写入 raw/meta/summary/report/stdout；本报告只出现 token 文件路径与长度 |
| TLS | `ssl.create_default_context()` 默认证书校验（OpenSSL 1.1.1t  7 Feb 2023）；仅在证书错误时回退并如实标记（本次探测未触发回退） |
| 探测时间窗 | 旧服务 `accept_until=2026-10-26T04:00:00+00:00`，`expires_at=2026-10-26T10:20:46+00:00`；当前 UTC `2026-10-24T09:28:34.315Z`，窗口仍开放 |

## 2. 静态搜索：九题正式入口配置 / 地址 / token / CLI

搜索范围：`E:\dev\agents\lark-working` 递归文本文件（≤2 MiB），共扫描 **756** 个文件；
排除 `.git`、`.lark-cli`（飞书凭据目录）、`__pycache__`、`node_modules` 与本次 probes 输出目录。

关键词命中：

- `nine_task_binding`：命中 6 个文件 —— `deliverables/2026-10-24-nine-task/REPORT.md`（行15,149,154）、`deliverables/2026-10-24-nine-task/publish.py`（行75）、`deliverables/2026-10-24-nine-task/evidence/contracts/contract-verification.json`（行11635,11636）、`deliverables/2026-10-24-nine-task/evidence/contracts/verify_contracts.py`（行1856）、`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md`（行59,74）、`inbox/1024-test/自主实验赛道选手公开包/docs/运行档.md`（行89）
- `nine_organizer_config_schema`：命中 4 个文件 —— `deliverables/2026-10-24-nine-task/evidence/contracts/contract-verification.json`（行5574,5576,5577）、`deliverables/2026-10-24-nine-task/evidence/contracts/verify_contracts.py`（行912,913）、`inbox/1024-test/自主实验赛道选手公开包/contracts/configuration-template.json`（行2）、`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md`（行37）
- `deployment_qualified_true`：**0 命中**
- `nine_service_deployed_flag`：命中 6 个文件 —— `deliverables/2026-10-24-nine-task/REPORT.md`（行15,38,143）、`deliverables/2026-10-24-nine-task/publish.py`（行74）、`deliverables/2026-10-24-nine-task/evidence/contracts/contract-verification.json`（行3617,3619,5557）、`deliverables/2026-10-24-nine-task/evidence/contracts/contract-verification.md`（行45）、`deliverables/2026-10-24-nine-task/evidence/contracts/verify_contracts.py`（行503,909,1068）、`inbox/1024-test/自主实验赛道选手公开包/release.json`（行42）
- `challenge_ids_null`：命中 2 个文件 —— `deliverables/2026-10-24-nine-task/evidence/contracts/contract-verification.json`（行5564,11909）、`inbox/1024-test/自主实验赛道选手公开包/contracts/rules-v1.json`（行593）
- `challenge_id_assignment`：命中 1 个文件 —— `work-context/maps/embodied-competition-hosting.md`（行105）
- `attempt_id_assignment`：命中 3 个文件 —— `deliverables/2026-10-22-challenge-spec-v3.md`（行162）、`deliverables/2026-10-22-grader-interface-card.md`（行44）、`work-context/maps/embodied-competition-hosting.md`（行104,122）
- `organizer_cli_invocation`：命中 2 个文件 —— `deliverables/2026-10-24-nine-task/REPORT.md`（行154）、`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md`（行81,84,88）
- `playground_submit_invocation`：命中 10 个文件 —— `.tmp/threshold_why.out`（行97）、`.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl`（行66）、`.tmp/sessions/3-session-138b9575-2926-4bb0-aed6-09dc0813944b.jsonl`（行32,41,42）、`deliverables/2026-10-22-challenge-statement-v3.md`（行180,282）、`deliverables/2026-10-22-challenge-statement.md`（行22）、`deliverables/2026-10-22-group-message.md`（行6）
- `challenge_id_cli_flag`：命中 4 个文件 —— `.tmp/threshold_why.out`（行97）、`.tmp/sessions/3-session-138b9575-2926-4bb0-aed6-09dc0813944b.jsonl`（行42,57,58）、`deliverables/2026-10-22-challenge-statement.md`（行22）、`inbox/2026-10-22-lab-agent-platform/platform/BOHRIUM_HANDOFF.md`（行16,18,20）
- `playground_token_env`：命中 1 个文件 —— `.tmp/sessions/3-session-138b9575-2926-4bb0-aed6-09dc0813944b.jsonl`（行58）

- 这说明 `nine_task_binding` 只出现在**文档/规则/同任务核验产物**中（`docs/平台接口.md`、`docs/运行档.md` 等），没有任何一条是“已部署服务配置”；`deployment_qualified=true` 在工作区**0 命中**（部署配置不存在）。
- `challenge_id` / `attempt_id` 只出现在旧平台的字段草案文档、术语表和通信记录里（`deliverables/2026-10-22-*`、`work-context`），不是本题平台配置；`playground submit` / `--challenge-id` 的命中也都是旧交接文档里的**示例命令**，没有任何一条绑定本题 Challenge ID。

候选服务 URL（过滤后）：

- `http://127.0.0.1:8090`（来源：.tmp/eval_inspect.out:116、.tmp/eval_logs.out:7、.tmp/eval_stage.out:25）
- `https://play.bohrium.com/api/docs/agent-workflow`（来源：.tmp/threshold_why.out:97、.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:66、.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:66）
- `https://play.bohrium.com/api/docs/compete-and-submit`（来源：.tmp/threshold_why.out:97、.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:66、.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:66）
- `https://play.bohrium.com/api/docs/arm-bundles`（来源：.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:66、.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:66、.tmp/sessions/3-session-138b9575-2926-4bb0-aed6-09dc0813944b.jsonl:32）
- `http://127.0.0.1:8090/v1/evaluations?task_id=basket_place&robot=dual_piper&seed=0`（来源：.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:403、.tmp/sessions/10-session-a580aa32-30a9-4f85-94bb-77f33473a469.jsonl:403、inbox/LOCAL_EVALUATION.md:76）
- `https://play.bohrium.com/competition/pku`（来源：.tmp/sessions/3-session-138b9575-2926-4bb0-aed6-09dc0813944b.jsonl:42、.tmp/sessions/3-session-138b9575-2926-4bb0-aed6-09dc0813944b.jsonl:42、inbox/2026-10-22-lab-agent-platform/platform/BOHRIUM_HANDOFF.md:3）
- `https://8787-direct-infra-spot--bohr-t238920-r1-lfpf5.ali-bohr-sandbox-a100.bohrium.com`（来源：inbox/lab-embodied-pilot-20261023/participant-kit/AGENT_GUIDE.md:12、inbox/lab-embodied-pilot-20261023/participant-kit/service.json:3、work-context/sources/2026-10-23/lab-embodied-pilot-participant-run.md:12）

CLI / 模块核查：

- `python -m organizer`：**未安装**（`organizer` 模块不存在，公开包只含 `lab_sdk` 打包工具，见 `inbox/1024-test/自主实验赛道选手公开包/SUBMISSION.md:67`）
- `lab_sdk` / `lab_platform` / `lab_nine` 模块：{"organizer": false, "lab_sdk": false, "lab_platform": false, "lab_nine": false, "lab_nine_sdk": false}
- PATH 可执行：{"organizer": null, "lab_eval": null, "lab_nine": null, "nine": null, "upload": null, "bohrium": null, "playground": "C:\\Users\\86150\\AppData\\Roaming\\npm\\playground.CMD"}
- 本机 127.0.0.1 候选监听端口：{"8090": "closed", "8787": "closed", "8888": "closed", "8890": "closed", "9000": "closed"}（`docs/平台接口.md` 说明本地组织者 HTTP 仅绑定 `127.0.0.1`，见 `inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:114`；本机无 8090/8787/8890 监听）
- 环境变量（只记名与长度）：[]
- 已知 CLI/配置候选文件存在性：{"organizer_module": null, "candidate_paths": {"inbox/1024-test/自主实验赛道选手公开包/lab_sdk/packaging.py": {"exists": true}, "inbox/lab-embodied-pilot-20261023/participant-kit/lab_eval.py": {"exists": true}, "inbox/lab-embodied-pilot-20261023/participant-kit/submission_bundle.py": {"exists": true}}}

### 2.1 平台 CLI 入口核查（只读命令）

> **结论：平台侧官方 CLI 通道存在且已认证，但本题 Challenge ID 未配置、平台可见 Challenge 中也没有本题题目。**
> 因此“有 CLI”不等于“本题正式入口可用”：没有 Challenge ID 时无法创建正确的 Attempt。

| 项 | 值 |
|---|---|
| CLI | `C:\Users\86150\AppData\Roaming\npm\playground.CMD`（`Playground CLI 0.1.40`，npm 包 `@paper2arm/playground-cli`） |
| 认证状态 | `authenticated=True`；`api_base=https://play.bohrium.com/api` |
| 凭据文件 | `C:\Users\86150\.config\playground\credentials.env`（存在：`True`；只记录键名 `['PLAYGROUND_TOKEN']`，**未读取/未输出其值**） |
| 本地平台配置 | `C:\Users\86150\.playground\config.json`（存在：`False`） |
| `submit` 语义 | `contains_create_attempt=True`；命令模板：`playground submit --challenge-id ID --outputs outputs-dir [--trace native-trace] [--raw-messages raw.jsonl] [--model MODEL] [--harness HARNESS] [--bundle-out playground-arm.zip] [--dry-run]` |
| 可见 Challenge 总数 | `6932`（`task list --limit 7000 --json` 返回 `6932` 条） |
| 本题九题 Challenge 是否可见 | **`False`** |
| 执行的只读命令 | `playground --help`、`playground auth status`、`playground submit -h`、`playground status -h`、`playground task list --limit 7000 --json` |
| 明确未执行的命令 | playground submit（会创建 Attempt=POST）；playground auth login/register（写凭据/建号）；playground task download/upload/upload-package（写平台）；playground status --attempt-id（无 Attempt） |
| CLI 判定 | 官方 Playground CLI 存在且已认证（api_base=https://play.bohrium.com/api）；但全量可见 Challenge 6932 个中未发现本题九题具身实验 Challenge，且工作区无 Challenge ID 配置；submit 会创建 Attempt（POST），按约束未执行。 |
| 原始证据 | `raw/cli-playground-entry-evidence.json` |

关键词强匹配（`nine / 九题 / embodied / 具身 / franka / piper / manipulat / 自主实验 / isaac / grasp / bottle_transfer / beaker_place / balance_load / stirrer_knob / tube_insert / lab-nine / robot arm`）
命中 24 条，经人工核对**没有一条**是本题九题具身实验 Challenge（命中主要来自 `nine-gene`、`nine-point`、`manipulator` 等子串，以及一条“电解液自主实验闭环”化学挑战，与本包台面/天平任务无关）：`tcp-http-eb4cb29a`；`hierarchical-clustering-and-gene-signature-discove-132bc797`；`wang-2020-prx-symplectic`；`hybrid-dft-reproduction-of-h-and-o-impurity-deep-t-ac42735b`；`two-step-multiscale-free-energy-calculation-on-ala-dc2e74ac`；`quantum-chemical-conformational-analysis-of-alkali-f8ba7d13`；`scef-conformational-search-on-polyalanine-3929b4d6`；`dft-frontier-molecular-orbital-analysis-compute-ho-b3c91a35`；`adiabatic-electron-affinity-of-adenine-water-compl-084fe5f9`；`spin-wave-polarization-manipulation-via-synthetic-a3f0be81`；`compute-bond-length-alternation-vertical-excitatio-ba5f6cc1`；`localized-vibrational-mode-frequencies-in-a-nine-a-e945494f`。

- 若平台后续发布本题 Challenge，正式提交命令将是 `playground submit --challenge-id <本题ChallengeID> --outputs <output-dir> --trace <session.jsonl>`；
  该命令会**创建 Attempt 并上传 bundle（POST/写操作）**，超出本核验任务“只读、非破坏性”的授权范围，故未执行。
- 本次也没有执行 `auth login/register`、`task download/upload`、`submit`，因此平台侧没有产生任何本题 Attempt 或提交记录。

边界说明：未递归扫描工作区之外的主机目录。理由：九题组织者部署代码按公开包声明另包交付（docs/发布接入清单.md：公开包不含服务器管理脚本，组织者部署代码另包），工作区即本次任务共享文件系统范围。仅列出一层父目录名作为边界记录。

## 3. 网络探测结果（非破坏性 GET）

目标地址来自旧包 `inbox/lab-embodied-pilot-20261023/participant-kit/service.json`：
`https://8787-direct-infra-spot--bohr-t238920-r1-lfpf5.ali-bohr-sandbox-a100.bohrium.com`

| # | 探测 | 鉴权 | HTTP | content-type | body bytes | body sha256（前缀） |
|---|---|---|---|---|---|---|
| 1 | `health_noauth` | 无 | 200 | application/json | 94 | `2eec015560e6f5a0…` |
| 2 | `tasks_noauth` | 无 | 401 | application/json | 29 | `55a8d8e7d1df1868…` |
| 3 | `tasks_auth` | Bearer | 200 | application/json | 2444 | `0f6a8ead3d5c8364…` |
| 4 | `challenges_auth` | Bearer | 404 | application/json | 26 | `5e6293a28b9df9bd…` |
| 5 | `attempts_auth` | Bearer | 404 | application/json | 26 | `5e6293a28b9df9bd…` |
| 6 | `evaluations_list_auth` | Bearer | 404 | application/json | 26 | `5e6293a28b9df9bd…` |
| 7 | `root_noauth` | 无 | 401 | application/json | 29 | `55a8d8e7d1df1868…` |
| 8 | `port8787_health_noauth` | 无 | 无响应 | - | 0 | `e3b0c44298fc1c14…` |
| 9 | `port8090_health_noauth` | 无 | 无响应 | - | 0 | `e3b0c44298fc1c14…` |
| 10 | `port8890_health_noauth` | 无 | 无响应 | - | 0 | `e3b0c44298fc1c14…` |

原始响应保存在 `raw/`（每条含 `.meta.json` 记录 UTC、method、URL、状态、响应头、body sha256）。

关键判定（逐条完整版见 `probe-summary.json` 的 `probes[].judgment`）：

- `GET /health`：200，`{schema: lab-eval-pilot-health/v1, status: ok}` —— 旧联调服务存活；
- `GET /v1/tasks`：无鉴权 401 `UNAUTHORIZED`；带 token 200 —— 需要旧服务 team token（token 文件有效）；
- `GET /v1/challenges`、`GET /v1/attempts`、`GET /v1/evaluations`（列表）：全部 **404 `NOT_FOUND`** —— 旧服务不存在 Challenge / Attempt 概念与对应路由；
- `/` 未鉴权 401；同域候选端口 `:8787`、`:8090`、`:8890` 的 `/health` 均连接超时 —— 该域名只通过 443 反向代理到旧服务，没有可直连的其它入口。

### 3.1 服务身份（`GET /v1/tasks`，鉴权后）

- HTTP 状态：**200**（无鉴权同一路径返回 401 `UNAUTHORIZED`，说明该 catalog 需 team token）
- 响应 `schema`：`lab-eval-pilot-catalog/v1`；其中 `catalog.schema`：`lab-task-catalog/v1`
- `benchmark_id`：`lab-agent-v0.4-five-tasks-dev`（响应 `catalog.benchmark_id`：`lab-agent-v0.4-five-tasks-dev`；旧 `service.json` 声明：`lab-agent-v0.4-five-tasks-dev`）
- 任务数：**5**，任务 ID：`bottle_transfer, beaker_place, balance_load, stirrer_knob, tube_insert`
- 任务明细：`balance_load`(development/basic, competition_ready=False)、`beaker_place`(development/basic, competition_ready=False)、`bottle_transfer`(development/basic, competition_ready=False)、`stirrer_knob`(development/basic, competition_ready=False)、`tube_insert`(development/basic, competition_ready=False)
- replicas：`4`；scope 上限：`{"full": 20, "smoke": 4}`
- worker 在线：`{"dual_piper": true, "franka": true}`；旧服务 `service.json` 声明 `competition_ready=False`
- 策略限制：`{"policy_cpu_seconds": 120, "policy_wall_seconds": 600, "policy_memory_bytes": 2147483648, "policy_network": "none", "policy_runtime": "python-stdlib-chroot-seccomp"}`
- 窗口（响应实时值）：`accept_until=2026-10-26T04:00:00+00:00`、`expires_at=2026-10-26T10:20:46+00:00`
- 响应是否含 `challenge` 字段：`False`；是否含 `attempt` 字段：`False`

### 3.2 九题新后端必备字段是否出现

`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:52` 要求 `GET /v1/tasks` 额外提供 `runtime_profile_sha256`、`configuration_sha256`、`runtime_capabilities`、`nine_task_binding`。
旧服务响应中的出现情况：

```json
{"nine_task_binding": false, "runtime_profile_sha256": false, "configuration_sha256": false, "runtime_capabilities": false}
```

**缺失字段**：`nine_task_binding`、`runtime_profile_sha256`、`configuration_sha256`、`runtime_capabilities`

## 4. 为什么旧五题服务不能冒充九题正式入口

1. **规则身份不同**：本题规则身份为 `lab-nine-20261024-v1`（`release.json` / `contracts/rules-v1.json`），旧服务 `benchmark_id=lab-agent-v0.4-five-tasks-dev`，是旧五题开发服务；公开包明确说旧服务不是统一九题服务——`inbox/1024-test/自主实验赛道选手公开包/SUBMISSION.md:65`：“开发可先使用公开instruction/observation样例验证策略。只有明确登记为兼容本版模型/图像运行档的开发入口，才接受新派生包。旧标准库五题服务的full=20、四题服务的full=16，不是统一九题服务。”
2. **正式入口由平台配置提供，不是旧服务**：`inbox/1024-test/自主实验赛道选手公开包/SUBMISSION.md:67`：“正式Playground登录、Challenge ID、产物上传命令与会话trace位置由该题实际平台配置提供。当前打包工具不执行正式提交、不读平台凭证。平台接入后提交一次，保存Attempt ID；组织方将它可信绑定到九题evaluation ID，保留两组child evaluation身份。”；`inbox/1024-test/自主实验赛道选手公开包/SUBMISSION.md:67`：“正式Playground登录、Challenge ID、产物上传命令与会话trace位置由该题实际平台配置提供。当前打包工具不执行正式提交、不读平台凭证。平台接入后提交一次，保存Attempt ID；组织方将它可信绑定到九题evaluation ID，保留两组child evaluation身份。”
3. **旧服务只有五题 full=20**：`inbox/lab-embodied-pilot-20261023/README.md` 自述“组织者另行发放队伍 token。包内含 CLI、示例提交 ZIP、公开观测、评分合同及真实回执；不含凭证。两条赛道各20回合完整实测已经返回有效最终开发分，空策略预期均为0。本服务接单截止北京时间2026-10-26 12:00，资源最早18:20:46到期。这是固定布局、标准库Python策略的邀请联调服务；正式隐藏集、模型代理和Playground榜单仍待接入。”；其任务/评分范围是五题×四重复=20 槽，而本题要求九题×四重复=36 槽（`docs/自主实验赛道PLAYGROUND题面.md` “九题等权…36 个回合”）。
4. **九题正式提交需要平台侧 Challenge/Attempt 认证与上传通道**：`inbox/1024-test/自主实验赛道选手公开包/docs/发布接入清单.md:10`：“| Playground | 一个Attempt映射一个机器人完整36槽，物理分0–100直接作为显示分，无额外trace倍率 | 两赛道Challenge ID、可信user/Attempt/artifact输入、回调鉴权/schema、幂等重放/乱序/错误处理及榜单读回 |”；`inbox/1024-test/自主实验赛道选手公开包/docs/发布接入清单.md:3`：“本地冻结版本 `lab-nine-20261024-v1`。参与者题面在 `自主实验赛道PLAYGROUND题面.md`；本页为组织者交接，不复制为选手操作步骤。用户已确认本轮包括模型和图像依赖运行档；Playground目前未配置，由用户与平台同事沟通，不重复索要Challenge。”
5. **本包没有官方回调/Attempt 凭据**：`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:5`：“**本地 HTTP 与真实 loopback 合同测试不等于正式平台接入或新运行档的 36 回合原生验收。** 本模块没有 Playground Challenge／Attempt／官方回调凭据，没有榜单写入。所有结果保持 `playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`。`scoreIsFinal` 只表示本地完整物理分聚合。”；`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:166`：“正式Playground再完成可信Attempt产物接入、官方回写schema／鉴权／幂等、分数量纲与trace规则、非零非满分回写及榜单读回。当前没有可执行的官方回调命令，也不需要为未知平台ID暂停本地公开包冻结。”
6. **新后端绑定字段必须由新 worker runtime 服务端绑定，本包未启用**：`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:74`：“新后端接受状态、轮询状态和结果同样须携带 `nine_task_binding`、从实际提交 manifest 核得的 `canonical_source_sha256`。已有两种 result schema 的其他字段保持其波次语义。这些字段需要安装、连接新 worker runtime 后由服务端绑定；本包没有偷偷修改或启用旧生产服务。`runtime.worker_hooks.TrialRuntime` 是新回合 runtime 接入点，不能仅因它存在就将服务资格设为 true。”
7. **部署模板不能启动正式评测**：`inbox/1024-test/自主实验赛道选手公开包/SUBMISSION.md:31`：“运行档SHA与配置SHA必须取自该比赛实际发布的配置；不要自己填64个零，也不要沿用旧五题/四题服务的配置。题包的 `contracts/configuration-template.json` 是本地预览配置，地址为空且部署资格为false，可用于本地打包检查；它不能启动正式评测。统一配置绑定九题规则、运行档、两组后端和资格身份。尚未激活的新配置只能用于本地检查，不能向旧服务提交模型运行档。”；`inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:35`：“`contracts/configuration-template.json` 是可打包的真实本地预览锁：规则和模型／图像 profile 的摘要来自本版文件。它保留已知原后端身份，两个 `url=null`、`deployment_qualified=false`。第一波旧公开服务没有资产／profile 身份字段，模板明确为 null；没有用虚构 SHA 补齐。该模板**不能提交到旧线上服务**。”；模板 `deployment_status="local_preview_only_not_a_live_evaluation_service"`，两个后端 `url=null`、`deployment_qualified=false`（`inbox/1024-test/自主实验赛道选手公开包/contracts/configuration-template.json:32,42`、`inbox/1024-test/自主实验赛道选手公开包/contracts/configuration-template.json:37,47`）。
8. **旧服务文档自述只是邀请联调**：`inbox/lab-embodied-pilot-20261023/participant-kit/AGENT_GUIDE.md:15`：“这是邀请联调服务，不是正式 Playground 榜单页面。当前接单截止为北京时间 2026 年 10 月 26 日 12:00，资源最早到期为 18:20:46。每次先调用 `tasks`，读取服务实际窗口和对应 worker 的 `online` 状态。”；`inbox/lab-embodied-pilot-20261023/README.md:5` 说明接单截止为北京时间 2026-10-26 12:00，是旧联调窗口，`inbox/1024-test/自主实验赛道选手公开包/docs/发布接入清单.md:19`：“`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false` 保持至实际接入验收。规则/SDK/运行档的本地冻结与模型依赖资格分别有证据字段；不以本地测试声称正式上线。现有开发服务10月26日12:00接单截止与订单租期是旧联调窗口，不能照抄为新比赛赛期。”。

## 5. 公开包自述的平台接入状态

- `release.json`：`live_nine_task_service_deployed=false`、
  `new_runtime_native_full36_verified=false`、
  `playground_integrated=false`、
  `official_score_writeback_verified=false`、
  `competition_ready=false`（`inbox/1024-test/自主实验赛道选手公开包/release.json:42`、`inbox/1024-test/自主实验赛道选手公开包/release.json:44`、`inbox/1024-test/自主实验赛道选手公开包/release.json:46`）
- `contracts/rules-v1.json` 的 `platform` 块（`inbox/1024-test/自主实验赛道选手公开包/contracts/rules-v1.json:589`、`inbox/1024-test/自主实验赛道选手公开包/contracts/rules-v1.json:593`）：
  `challenge_ids=null`、`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`
- `README.md`：`inbox/1024-test/自主实验赛道选手公开包/README.md:15`：“发布文件身份和证据范围见 `release.json`、`PUBLIC-MANIFEST.json`。规则、SDK、依赖运行档的冻结与云端统一36槽部署、Playground正式接入分别记录；正式平台未完成绑定前，`competition_ready=false`。无需发布或创建Challenge即可在本地复核这些产物。”
- 题面：`inbox/1024-test/自主实验赛道选手公开包/docs/自主实验赛道PLAYGROUND题面.md:72`：“4. 通过当前题目页的正式入口提交这些产物及平台要求的真实开发轨迹，保存返回的 Attempt ID，查询这一次提交。”；`inbox/1024-test/自主实验赛道选手公开包/docs/自主实验赛道PLAYGROUND题面.md:76`：“策略的自报分数、演示视频和本地结果不能代替官方复测。公开包和平台正式接入清单分别提供下载；题包中的检查、打包、开发取分与正式 Playground 提交是不同操作。准确命令见 `SUBMISSION.md`，正式 Challenge 与登录命令由本页面实际接入配置提供。”

## 6. 判定

> **正式提交不可执行、Attempt ID 无法在不伪造的前提下取得。**

依据列表见 `probe-summary.json` 的 `conclusion.reasons`。本次探测：
- 没有创建任何评测或 Attempt（含平台 CLI：未执行 `playground submit`）；
- 没有取得任何 Attempt ID / evaluation ID / 分数；
- 没有把旧五题服务的返回值当作九题结果；
- 没有用无关 Challenge 做“试提交”（平台可见 Challenge 与本题无关）；
- 未在任何输出文件中写入 token。

要让九题正式提交可执行，仍需平台侧提供（按 `inbox/1024-test/自主实验赛道选手公开包/docs/发布接入清单.md:19` 与 `inbox/1024-test/自主实验赛道选手公开包/docs/平台接口.md:50`）：

1. 本题两赛道 **Challenge ID**（当前 `challenge_ids=null`，平台可见 Challenge 中未发布本题题目）——这是当前唯一缺口的“入口”本身；
2. 本题 Challenge 的 **playground submit 提交入口**（CLI 已安装且已认证，拿到 Challenge ID 后即可按 `playground submit --challenge-id <ID> --outputs <dir> --trace <session.jsonl>` 执行，但该命令会创建 Attempt，属写操作）；
3. 可信 **user/Attempt/artifact** 输入、回调鉴权/schema、幂等重放与榜单读回；
4. 新 worker 运行档的 36 槽原生验收与官方回写读回验证（`deployment_qualified=true` 且 `competition_ready=true` 之后）。

## 7. 产物

| 文件 | 内容 |
|---|---|
| [`probe_entry.py`](probe_entry.py) | 本探测脚本（可复跑：`D:\python\python310\python.exe probe_entry.py`） |
| [`probe-summary.json`](probe-summary.json) | 机器可读证据：静态搜索、平台 CLI、citations、每条探测状态+sha256+判定、结论 |
| [`probe-report.md`](probe-report.md) | 本报告 |
| `raw/` | 原始响应 body（`.json`/`.txt`）+ 每条探测的 `.meta.json`（UTC/method/URL/状态/响应头/body sha256）；另含平台 CLI 只读查询证据 `raw/cli-playground-entry-evidence.json` |

token 泄漏终检：检查 `24` 个文件，泄漏文件：`无`。

---

*本报告由 `probe_entry.py` 生成，所有行号引用由脚本按原文检索得到；所有网络结论均可在 `raw/` 中按 sha256 复核。*
