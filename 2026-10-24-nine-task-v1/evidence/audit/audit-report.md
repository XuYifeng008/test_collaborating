# 独立红队审计报告（lab-nine-20261024-v1 参评交付）

- 审计人：独立红队审计员（red-team-auditor，只读为主、独立复算/复跑，不信任 Lead 报告数值）
- 审计时间：2026-10-24 17:31–17:46（Asia/Shanghai）
- 被审版本（最终态）：GitHub `XuYifeng008/test_collaborating` main = `a36d439e5da279a8c982ff96353b1579d14bc14c`；工作区 `deliverables/2026-10-24-nine-task/`（REPORT.md 29,998 B / SHA256 `feeb195b…`，最后修改 17:34:01）
- 审计方法：自写 Python 脚本独立重算哈希、从零重建 ZIP、复跑 `lab_sdk.adapters.Adapter`、复跑测试套件与 wrapper 往返、解析 probe 原始响应、回读 GitHub git 对象；未修改 `src/`、`outputs/`、`tests/`、`REPORT.md`、公开包或 GitHub
- 结论口径：允许“无法判定”；任何伪造分数/Attempt/成功声明按最高优先级 FAIL 处理

---

## 0. 总结论

**可交付（建议修复 3 处低严重度报告数据笔误，不阻塞交付）。**

- **诚实性（最高优先级）：PASS。** 未发现任何伪造的 Attempt ID、evaluation ID、36 槽分数、任务成功声明或“已提交/已得分”表述；未把空策略、上传成功、本地 mock 当作成功。REPORT 的“无正式入口、不伪造”结论与 `release.json`、`contracts/rules-v1.json`、`contracts/configuration-template.json`、`evidence/probes/` 实测完全一致。
- **产物一致性：PASS。** 两赛道各 4 个文件齐全；我独立重算的 `canonical_source_sha256`、两赛道全部 ZIP/receipt 字节哈希、两赛道 `canonical.zip` 字节相同、ZIP 成员（entry.py/lab_sdk/canonical/wrapper 内容）全部与官方 `lab_sdk.packaging` 语义一致；我按官方算法从源码**从零重建 ZIP，字节完全一致**。
- **测试真实性：PASS。** 我亲自复跑 `D:\python\python310\python.exe -B deliverables\2026-10-24-nine-task\tests\run_tests.py --no-write`：退出码 0、**17 PASS / 0 FAIL / 0 ERROR**（39.16 s；归档 34.59 s，仅环境耗时差异，检查项/计数/统计一致）；`test-results.json` 与 `TEST_RESULTS.md` 17 行逐项一致；synthetic/运动学 mock 标注明确。
- **报告数据抽查：PASS，但发现 3 处不实数据（低严重度）**：源码字节数 66,335（应为 66,636）、C07 首次 finish 步数 2418（证据为 2448）、C07 nominal “tare 后 9 次 read”（数据为 tare 后 7 次、总 9 次）。均为报告笔误，不涉及任何分数/Attempt/产物，故不阻塞；建议按 §6 修复。
- **GitHub 回读：PASS。** 远端 main = 本地 HEAD = `a36d439`；campaign 目录 61 个文件与 deliverables 对应文件**逐字节一致**（git blob 亦一致）；campaign `README.md` 与本地 `REPORT.md` 逐字节相同。

> 证据文件：本目录 `audit-report.md`、`audit-findings.json`。

---

## 1. 诚实性（最高优先级）——PASS

逐项核对与独立取证：

1. **伪造身份/分数扫描：PASS（0 命中）**
   - 对 deliverables + GitHub campaign 共 105 个文本文件做模式扫描：
     - `attempt_id`/`evaluation_id` 赋值式出现：**0**；
     - `eval-<hex>` 形式旧评测 ID：**0**；
     - 数值型 `"score": <number>` 字段：**0**；
     - 中文成功类表述（已提交成功/已得分/获得 N 分/最终得分/满分/36/36/全部成功/排名第）：命中 30 处，逐条人工复核**全部为否定句、评分公式复算说明或“要求条件”**（如“未提交”“不伪造”“满分复算：100*sum(4/4 for 9)/9 == 100 == 100×36/36”“只认 scoreIsFinal=true 才可能”），无一条为“已获得”；
     - `scoreIsFinal=true`/`scored_count=planned_count=36`：共 12 处，全部出现在“判据/要求/本轮客观不存在”的上下文中，无 Achievement 断言；
     - UUID 形式命中 42 处，逐条核对**全部是 `.tmp/sessions/*.jsonl` 会话文件名**（probe 报告引用其行号作为静态搜索来源），**无任何 Attempt ID/评测 ID**。
2. **结论一致性：PASS**
   - `release.json` 实测：`live_nine_task_service_deployed=false`、`playground_integrated=false`、`official_score_writeback_verified=false`、`competition_ready=false`、`new_runtime_native_full36_verified=false`、`external_model_api_qualified=false`（第 41–46 行）；
   - `contracts/rules-v1.json` 第 589–597 行 `platform.challenge_ids=null`、三个平台 flag 均 false；
   - `contracts/configuration-template.json` 第 30–51 行两后端 `url=null`、`deployment_qualified=false`，`deployment_status=local_preview_only_not_a_live_evaluation_service`；
   - `evidence/probes/raw/03_tasks_auth.body.json` 实测：`benchmark_id=lab-agent-v0.4-five-tasks-dev`、5 题、`replicas=4`、`scopes={"full":20,"smoke":4}`、缺 `nine_task_binding`/`runtime_profile_sha256`/`configuration_sha256`/`runtime_capabilities`、`native_qualification` 两机器人均为 `not_qualified_in_current_delivery`；`/v1/challenges`、`/v1/attempts`、`/v1/evaluations`（列表）原始响应均 404 `NOT_FOUND`；
   - 我另用官方 `playground` CLI（0.1.40）**只读复跑**：`--help`、`auth status`（authenticated=true, api_base=https://play.bohrium.com/api）、`submit -h`（含创建 Attempt 语义）、`task list --limit 7000 --json` 成功返回 **6932** 条；我对 6932 条做硬关键词（franka/piper/bottle_transfer/beaker_place/balance_load/stirrer_knob/tube_insert/lab-nine/nine_task/embodied/具身）扫描：**0 命中**，支持“本题九题 Challenge 未上架、无 Challenge ID、无法创建正确 Attempt”的结论。
3. **“未 POST/未上传/未创建评测”的取证一致性：PASS（证据支持）**
   - 10 条网络探测原始 meta 全部 `method=GET`，`probe-summary.method_policy` 记录 `http_methods_issued=["GET"]`、`created_evaluations_or_attempts=0`、`cli_mutations="none"`；原始 body 与 meta 的 sha256 全部复核一致；
   - 静态搜索 `deployment_qualified": true`（配置语义）在交付物与 campaign 中 **0 命中**；工作区也无监听 8090/8787/8890 的服务、无平台注入环境变量（我独立复核）；
   - 边界：无法从文件系统证明“过去从未发送过 POST”，只能证明交付物与原始证据中不存在 POST 痕迹与任何 ID/分数产物，且报告表述与证据一致（不虚报）。
4. **是否把空策略/上传成功/本地 mock 当成功：PASS。** 报告与测试明确写“无上传、无 0 分/满分记录、运动学 mock 非物理、synthetic 非真实数据”；测试用例命名/备注均为 `safe_abort_no_perception`、`synthetic`、`kinematic mock (NOT physics)`。
5. **空策略/0 分表述：PASS。** 仅出现在“把上传成功或空策略 0 分当作任务成功是明确禁止的，本报告不这样做”等否定句。

## 2. 产物一致性——PASS

独立复算（自写脚本，不复用 Lead 的 verifier；仅以公开 `lab_sdk.packaging` 源码为算法依据）：

| 检查 | 结果 |
|---|---|
| `outputs/`、`outputs-piper-dual/` 各 4 文件存在（canonical.zip/wave1.zip/wave2.zip/package-receipt.json） | PASS |
| 我重算 `canonical_source_sha256`（6 源文件 source hash）= `b6a78c5adfc3e5e891b1f7bcd5d6aba807e80be67f482842c2c0f663bf7246f4`，与两赛道回执一致 | PASS |
| 两赛道回执 `canonical_files`/`sdk_files`/`sdk_source_sha256=8bfc6839…`/`runtime_profile_sha256=b32b478e…`/`configuration_sha256=0e501779…` 与真实字节一致 | PASS |
| 我按官方算法从源码**从零重建** 4 个 ZIP 并逐字节比较：franka `canonical.zip=2735bb06…`、`wave1=f4e43152…`、`wave2=92323c48…`；piper-dual `canonical=2735bb06…`、`wave1=fc04a286…`、`wave2=d56052c1…`；rebuilt == actual == receipt 声明值 | PASS（字节完全相同） |
| 两赛道 `canonical.zip` 字节完全相同（67242 B / `2735bb06…`） | PASS |
| ZIP 可完整解压（`testzip()` 无错）、每个派生 ZIP 14 成员、含 `entry.py`/`lab_sdk/*`(6)/`canonical/*`(6)/`submission.json`；`entry.py` 内容精确为 `from lab_sdk.policy import make_policy\nPolicy = make_policy(__file__, '<wave>', '<robot>')\n` | PASS |
| `package-receipt.json` 自身字节/大小与 REPORT §3 表逐项一致（2,613 B/`8bb7058a…`；2,617 B/`64b1b9c9…`） | PASS |
| 确定性：官方打包算法下重建的 ZIP 字节与既有产物完全相同（两次重建亦相同） | PASS |
| 交付物与 GitHub campaign 的 8 个产物文件逐字节一致 | PASS |

## 3. 测试真实性——PASS

- **亲自复跑**：`D:\python\python310\python.exe -B deliverables\2026-10-24-nine-task\tests\run_tests.py --no-write`（`--no-write` 以遵守“不得修改 tests/”约束）→ **退出码 0**，`通过 17 / 失败 0 / 错误 0 / 跳过 0`，总耗时 39.16 s（归档 34.59 s，为机器负载差异；17 个用例的检查计数与归档完全一致）。各用例检查数：fixtures 61、adapter 698、frequency 72、joint 117、action 67、driver 36、policy 15、real 14/14/20/15、c07 29/22/22/22、synthetic 32/24。
- **JSON ↔ Markdown 一致性**：`tests/test-results.json` 的 `summary`（pass 17 / fail 0 / error 0）与 `TEST_RESULTS.md` 完全一致；17 个测试逐行比对 test_id/状态/通过/失败/警告计数，**17/17 行全部一致**；生成时间 `2026-10-24T09:28:11Z` 与 JSON meta 一致。
- **数据来源真实性**：JSON 记录的 6 个策略文件 bytes+sha256 与当前 `src/my-policy/` 真实字节**逐项一致**（说明归档结果确实针对当前冻结源码）；4 份真实 fixture 的 `source_release` 与原始 instruction sha256 与公开包 provenance 一致。
- **合成/非物理标注**：4 份真实 fixture vs **14 份 synthetic** 用例区分明确；`synthetic=True`、`kinematic mock (NOT physics simulation)`、`C07 balance receipts are scripted protocol stubs`、`synthetic perception stub` 均写入 JSON/MD 与用例备注；失败检查明细为“无失败检查”。
- **确定性**：4 个真实用例与 C07 nominal 的各 2 次运行动作 digest 完全相同（如 real:C07 run1=run2=`d8847d4a…`；c07 nominal run1=run2=`83be4366…`）。
- **C07 去皮**：nominal 用例 tare 恰好 1 次、无二次 tare、tare 前有 2 次有效 stable read、tare 后有效 stable net-mass read 6 次（总 read 9）、最终净质量 10.100 g 在 [9.5,10.5] 容差、`instrument` 从不与 `arms` 混合、finish 前保持 450 步；三组异常回执（unstable/missing/persistent）全部 PASS 且不重复 tare、不误报有效质量。
- 缺陷记录真实性：JSON/MD 记录“wave2 finish 前保持被截断 120 步 → 修复后 150 步（1.25 s）”与归档 real:C07/real:C02 `terminal_hold_steps=150` 一致。

## 4. 报告数据抽查——PASS（3 处低严重度 FAIL，见 §6）

| REPORT 引用 | 我的独立复核 | 判定 |
|---|---|---|
| 公开包 930 项检查、915 通过、0 问题、15 记录 | `contract-verification.json`：`checks_total=930`、`pass=915`、`fail=0`、`info=15`、`issues_total=0`；`checks` 数组实为 930 条且 status 分布 915 pass/15 info；6 个类别合计 930/915/15/0 自洽 | PASS |
| PUBLIC-MANIFEST 33/33 bytes+sha256 匹配 | 我独立重算：清单 33 条，逐条 bytes+sha256 **33/33 匹配**；包内实际文件 34（仅多清单自身）；清单排序/无重复 | PASS |
| 4 份真实 fixtures × Adapter 全部通过、合计 477 内部检查 | contract JSON：4 case 各自 checks_total=112/123/130/112、checks_pass 同值、fail=0，合计 **477**；动作矩阵 legal=8/9/11/8 全过、illegal=24/24/27/24 全拒；我另用官方 `Adapter` **亲自重跑 4 份 fixture**：wave 推断、统一臂映射（wave2 piper 原生 `arm`→`left`）、关节数（franka 7 / piper 每臂 6）、夹爪范围（wave1 [0,0.08]；wave2 franka [0,0.08]、piper [0,0.1]）、频率（240/120）、finish extra（720/0）、observation 臂映射、非法动作矩阵全部符合 | PASS |
| freeze 相关 SHA/wrapper 8 项/C07 tare=1 | freeze/包装回执已逐字节重算；wrapper 证据 8 条且我把 `wrapper_roundtrip.py` 复制到临时目录**独立复跑 → 8/8 与归档逐条相同**；C07 tare=1 见 §3 | PASS |
| 公开 PNG 感知冒烟（800×600×3、green/blue、白帽 blobs=4、fill≈0.57） | 我**独立复跑** `evidence/perception/perception_smoke.py` → 输出与 `evidence/logs/perception-smoke.log` 逐行一致（含 shape `(600, 800, 3)`、green/blue、blobs=4、fill=0.5720…） | PASS |
| 报告引用行号（release 42–46、rules 589–597、config 30–51、SUBMISSION/平台接口/发布接入清单等） | 抽查 14 处引用，行号与内容均对得上 | PASS |
| **源码 6 文件 66,335 B（§2）** | 实际 6 文件合计 **66,636 B**；REPORT §3 与 §8 均写 66,636 B | **FAIL（笔误）** |
| **C07 “finish 于 2418 步”（§2.2）** | `evidence/logs/lead-dev-tests.log` 实测 `steps=2448`；REPORT §4.3 亦写 `step 2448` | **FAIL（笔误）** |
| **C07 nominal “tare 后 9 次 read”（§4.2）** | `test-results.json` 的 `balance_stub.reads_after_valid_tare=7`（总 read=9） | **FAIL（笔误）** |
| C07 dev 记录 “finish step 2448，含 finish 前 150 步保持”（§4.3） | 日志为 `steps=2448` 但未记录 hold 步数，“含 150 步保持”无法由该日志复核（同套件 real:C07 hold=150 已由 tests 验证） | **无法判定（证据不足）** |
| “净质量 4.53→10.10 g 均在容差”（§4.2） | 起读 4.533 g 不在 [9.5,10.5] 容差，终值 10.100 在容差；措辞不精确 | 提示（非伪造） |
| token 泄漏 | 我读入 `inbox/colleague-test-01.token`（43 字符）后对工作区 955 个文件全量字节扫描（排除 token 文件自身/.git/.lark-cli/二进制）：**0 命中**；evidence 中无字面 `Bearer <token>`；token 未打印、未写入任何文件 | PASS |

## 5. GitHub 回读——PASS

| 检查 | 结果 |
|---|---|
| `gh api repos/XuYifeng008/test_collaborating/commits/main` = `a36d439e5da279a8c982ff96353b1579d14bc14c`；本地 `.tmp/github/test_collaborating` HEAD 相同、worktree clean | PASS |
| campaign `2026-10-24-nine-task-v1/` 共 61 个文件；与 deliverables 对应文件（README↔REPORT、outputs-franka↔outputs、outputs-piper-dual↔outputs-piper-dual、src/tests/evidence 同名）**逐字节一致：61/61** | PASS |
| `git ls-tree -r HEAD` 文件集合 = campaign 工作区文件集合（61/61）；HEAD blob 内容与 deliverables 一致（0 差异） | PASS |
| campaign `README.md` 与本地 `REPORT.md` 逐字节相同（29,998 B，SHA256 `feeb195b…`） | PASS |
| 仓库根 README 含 campaign 链接；无伪造 Attempt/分数陈述 | PASS |
| 说明 | 审计开始时曾读到旧版 `b1e2f5d`（其 evidence/probes 落后于交付物 17:31 的探测重跑）；Lead 刷新后的最终 `a36d439` 已包含更新后的 probes/perception 证据，本报告以 `a36d439` 为准，旧版本差异已消失 |

## 6. FAIL / 无法判定 / 提示 清单（按严重度）

| # | 级别 | 位置 | 问题 | 证据 | 建议修复 |
|---|---|---|---|---|---|
| F1 | 低（报告数据笔误） | `REPORT.md:44` | “6 个文件，源码 66,335 B” | 实际 66,636 B；同报告 :102、:232 正确 | 改为 66,636 B |
| F2 | 低（报告数据笔误） | `REPORT.md:71` | C07 “finish 于 2418 步” | `evidence/logs/lead-dev-tests.log` 为 2448；`:135` 为 2448 | 改为 2448 |
| F3 | 低（报告数据笔误） | `REPORT.md:130` | “tare 后 9 次 read” | 数据为 tare 后 7 次（总 9 次） | 改为 “tare 后 7 次 read（总 9 次）” |
| F4 | 无法判定（证据不足） | `REPORT.md:135` | dev 记录称 “含 finish 前 150 步保持” | 该日志未记录 hold 步数 | 可补记 hold 或删除该断言 |
| F5 | 提示（措辞） | `REPORT.md:130` | “净质量 4.53→10.10 g 均在容差” | 4.53 不在容差，仅终值 10.100 在容差 | 改为 “终值 10.100 g 在容差” |
| F6 | 提示（清单） | `REPORT.md:227-243` | §8 文件清单未列 `publish.py`（目录内实有 4,431 B） | 目录实测 | 补入清单 |
| F7 | 提示（格式） | `evidence/logs/perception-smoke.log` | UTF-8 BOM 前缀（重跑输出与内容一致） | 逐行对比 | 可忽略/重存无 BOM |

**未发现任何伪造分数 / Attempt / 成功声明，故无最高优先级 FAIL、无阻断项。** F1–F3 是报告文字与证据间的不一致（笔误级别），不改变“无正式入口、不伪造、产物真实”的结论。

## 7. 独立复算关键数值（供复核）

- `canonical_source_sha256` = `b6a78c5adfc3e5e891b1f7bcd5d6aba807e80be67f482842c2c0f663bf7246f4`
- `sdk_source_sha256` = `8bfc68398c0b4bde307c0a00e838baf3ed1db92504f1b27ca87518e6ed7f5cc8`
- franka：`canonical.zip` 67,242 B `2735bb06a066f8db79d2f2fbe16d2bea521ee6fa6302ef5e87cc4bce03deb26a`；`wave1.zip` 89,327 B `f4e43152182b4800fea7d52150e0933edc2759d07f6f019bc4886f5d01522ee4`；`wave2.zip` 89,327 B `92323c48abbd32c5161f918cbbb7bd2add3712ba182ee9eb90ef0f9cfc288a35`；receipt 2,613 B `8bb7058a02a439976c17344f70b20b93c530717ecae091c9198fed4085d32e0c`
- piper-dual：`canonical.zip` 同上字节；`wave1.zip` 89,335 B `fc04a286b6cead3bbdbae1271cc98efbde930580703aa2de1c2daba4dbfc2d23`；`wave2.zip` 89,335 B `d56052c172ad368881be67c0cf6c901e6cc7a44284b4cf2035a78c6330cb2fdb`；receipt 2,617 B `64b1b9c91a6bbd8fb921d0d4a52238cfda1ebbddb2492e29385b1ec381ea48d1`
- 公开包：rules 规范 JSON `e65b8edb…`、runtime-profile `b32b478e…`、configuration `0e501779…`、SDK source `8bfc6839…`、model-registry `9d60ca75…`、wheels.lock `dd495064…`（均与 release 互绑一致，独立重算）
- 测试复跑：exit 0；17/17 PASS；39.16 s（归档 34.59 s）
- wrapper 往返复跑：8/8 与归档逐条相同
- 感知冒烟复跑：与 `perception-smoke.log` 内容一致
- token：43 字符；扫描 955 文件，0 命中；未写入/未打印
- GitHub：`a36d439e5da279a8c982ff96353b1579d14bc14c`，campaign 61/61 文件一致

## 8. 审计边界

- 本审计为**参赛侧交付的独立复核**，不是官方评测；不改变“本轮无官方 Attempt/36 槽分数”的事实。
- 无法从静态证据证伪“历史上从未发生 POST/上传”，但交付物与原始探测证据中不存在任何上传/评测产物或 ID，且报告表述与证据一致；我另以官方 CLI 只读复跑（auth status/task list）验证了 CLI 通道存在、本题 Challenge 不可见（6932 条中硬关键词 0 命中）。
- probe 的 “strong_match_count=24” 与我在 17:44 复跑得到的 24 条集合成员略有差异（平台列表动态变化），数量一致、且均无本题九题题目；不构成矛盾，但“同一快照”无法复核。
- 我未修改 `src/`、`outputs/`、`tests/`、`REPORT.md`、公开包或 GitHub；仅写入本目录两个审计文件。公开包 `lab_sdk/__pycache__` 时间戳保持 17:14/17:17，未因审计产生新写入。
