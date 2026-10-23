# 实验室具身操作邀请联调 · 选手侧评测报告

> **2026-10-24 新增：真实策略联调结果** —— [2026-10-24-real-policy/README.md](2026-10-24-real-policy/README.md)：dual_piper 赛道 score_100=40.0（bottle_transfer 4/4 + stirrer_knob 4/4）、franka 赛道 score_100=20.0（stirrer_knob 4/4）；franka bottle_transfer 触发可复现的服务端原生复核错误（NATIVE_REQUIRES_REVIEW），详见该报告。

---

> 运行标识：`20261023-colleague-test-01`
> 执行时间：2026-10-23 22:27–23:05（Asia/Shanghai）
> 执行方式：Agent 按 participant-kit 的 `AGENT_GUIDE.md` 自动完成（tasks → pack → submit → wait → result）
> 服务 benchmark：`lab-agent-v0.4-five-tasks-dev`（交付包 build `pilot-20261023-build003`）
> 策略：官方空策略 `examples/idle`（不执行任何操作，预期 0 分，仅用于验证提交—评测—取分链路）
> 结论：**链路全通，三次评测均取得有效最终开发分，全部进程退出码 0。**

---

## 0. 敏感信息处理

- **token 未包含在本仓库任何文件中**，提交时仅通过 `--token-file <路径>` 传入；仓库中所有命令模板均用占位符。
- 组织者服务入口 URL 未写入本仓库（该地址在本地工具包 `service.json` 中，属邀请制联调入口）；本仓库只记录与结果解释相关的 benchmark 标识、任务 ID 与运行时限额。
- 本仓库只含本次真实回执、结果与自检脚本，均为公开结果字段，不含私有接触证据或裁判数据。

## 1. 结论

| # | 机器人 | 范围 | evaluation_id | 计划/有效 | 每题均值 | 分数 | 退出码 |
|---|---|---|---|---:|---|---:|---:|
| 1 | franka | smoke（`bottle_transfer`） | `eval-b90601645e814f1d8bc79931ebcf6ebc` | 4 / 4 | `bottle_transfer` = 0.0 | `score_100=0`（`single_task_smoke`） | 0 |
| 2 | franka | full（五题） | `eval-309fb00bad1741c98c35d430dda393fc` | 20 / 20 | 五题各 0.0 | `score_100=0`（`five_task_track`） | 0 |
| 3 | dual_piper | full（五题） | `eval-3261364aea8245e18f06379e30b34611` | 20 / 20 | 五题各 0.0 | `score_100=0`（`five_task_track`） | 0 |

- 三次均 `state=scored`、`scoreIsFinal=true`、`scored=true`、`physical_evaluation=true`，每题 4 个不同 trial 全部 `state=scored`、`reward∈{0,1}`（本次全 0）、`error_code=null`。
- `wait` 与随后 `result` 取回的内容完全一致；自检脚本 `evidence/verify_results.py` 复核通过（`ALL CHECKS PASSED`）。
- 一次提交、一次接受（HTTP 202 / queued），无重复提交、无 429、无 401、无 `requires_review`、无基础设施错误。
- **空策略 0 分是文档预期结果**，只证明"打包→上传→排队→起仿真→物理判分→取分"链路有效，不代表五题已被解出；当前 `competition_ready=false`，属于开发联调分，不是正式榜单成绩。

## 2. 评测环境与合同

| 项 | 值 |
|---|---|
| CLI | participant-kit 内 `lab_eval.py`（仅 Python 标准库） |
| Python | 3.10.11（Windows；见 §5 问题 1） |
| 服务入口 | 组织者单独提供的 HTTPS 邀请联调入口（本仓库不记录地址） |
| benchmark | `lab-agent-v0.4-five-tasks-dev`；策略接口 `lab-policy-v1`；instruction schema `lab-agent/v0.3` |
| worker | `franka.online=true`、`dual_piper.online=true` |
| 计划规模 | `replicas=4`；`smoke=4` 次、`full=20` 次 |
| 策略运行时 | `python-stdlib-chroot-seccomp`；CPU 120 s、策略墙钟 600 s、内存 2 GiB、无网络 |
| 接单截止 | `accept_until=2026-10-26T04:00:00Z` = 北京时间 2026-10-26 12:00 |
| 资源到期 | `expires_at=2026-10-26T10:20:46Z` = 北京时间 2026-10-26 18:20:46 |
| 公开身份 | `competition_ready=false`；固定布局 `five-task-scene-v0.4-fixed`；`seed_randomizes_layout=false` |

提交包（`examples/idle` 打包）：

| 项 | 值 |
|---|---|
| `submission_id` | `idle-example` |
| `source_sha256` | `3627ba432680e7cf0930629840e6197a163db0082732ff75af531b8d7ca1599f` |
| `archive_sha256`（本地实际上传 ZIP） | `5e1274ce60f5696edd1b6c47ac5e68bcaed6f33fc1fb2e743630d90312607ba4` |
| `backend_source_sha256`（服务端裁判/后端） | `a5bf914d0a721b3cee6a5d5931e8ed62320c7f01738798b0b9992084bc73ff33` |

## 3. 执行过程（命令级）

以下命令均为实际执行形式，token 路径用占位符替换；Windows 下 `python` 即 Python 3.10.11 解释器。

```powershell
# 1) 连接检查
python lab_eval.py tasks --token-file <TOKEN_FILE>

# 2) 打包（输出 ZIP 必须位于策略目录之外）
python lab_eval.py pack examples/idle --output <RUN>\idle.zip

# 3) 提交 smoke（单题 4 次）
python lab_eval.py submit <RUN>\idle.zip --robot franka --scope smoke `
  --task-id bottle_transfer --idempotency-key colleague-test-01-franka-smoke-001 `
  --receipt <RUN>\franka-smoke-accepted.json --token-file <TOKEN_FILE>

# 4) 等待并下载结果（已自动校验回执/哈希/次数/均值）
python lab_eval.py wait <EVAL_ID> --receipt <RUN>\franka-smoke-accepted.json `
  --timeout 7200 --poll 10 --output <RUN>\franka-smoke-result.json `
  --token-file <TOKEN_FILE>

# 5) 提交 full（五题 20 次；无需 --task-id）
python lab_eval.py submit <RUN>\idle.zip --robot franka --scope full `
  --idempotency-key colleague-test-01-franka-full-001 `
  --receipt <RUN>\franka-full-accepted.json --token-file <TOKEN_FILE>
python lab_eval.py submit <RUN>\idle.zip --robot dual_piper --scope full `
  --idempotency-key colleague-test-01-piper-full-001 `
  --receipt <RUN>\dual_piper-full-accepted.json --token-file <TOKEN_FILE>

# 6) 分别 wait + result 复取
python lab_eval.py wait <EVAL_ID> --receipt <RUN>\<STEM>-accepted.json --timeout 7200 --poll 10 `
  --output <RUN>\<STEM>-result.json --token-file <TOKEN_FILE>
python lab_eval.py result <EVAL_ID> --receipt <RUN>\<STEM>-accepted.json `
  --output <RUN>\<STEM>-result-copy.json --token-file <TOKEN_FILE>
```

时间线（UTC 为回执时间，北京 = UTC+8）：

| 步骤 | 提交（UTC / 北京） | 终态（UTC / 北京） | 用时 |
|---|---|---|---:|
| smoke | 14:29:02 / 22:29:02 | 14:33:44 / 22:33:44 | ≈ 4 分 41 秒 |
| franka full | 14:34:06 / 22:34:06 | 14:57:50 / 22:57:50 | ≈ 23 分 44 秒 |
| dual_piper full | 14:34:25 / 22:34:25 | 14:58:28 / 22:58:28 | ≈ 24 分 03 秒 |

> 说明：用户只要求跑一次 full；本次在 franka full 完成后，额外提交 dual_piper full，以覆盖两个 online worker（文档允许、分开计分）。两条 full 在主赛道完成前并行提交，恰好占满"每团队最多 2 项未终结评测"的配额（见 §5 问题 9）。

## 4. 结果明细与自检

每个 `result_sha256` 由服务返回，是对 `result` 对象做 UTF-8、键排序、无多余空格、不转义非 ASCII 的规范 JSON 后取 SHA256；`idle.zip` 与回执/结果一起放在 `evidence/`，可用 `verify_results.py` 离线复现。

| 项 | smoke | franka full | dual_piper full |
|---|---|---|---|
| `state` | scored | scored | scored |
| `scoreIsFinal` / `scored` / `physical_evaluation` | true / true / true | true / true / true | true / true / true |
| `planned_count` / `scored_count` | 4 / 4 | 20 / 20 | 20 / 20 |
| `score_scope` | `single_task_smoke` | `five_task_track` | `five_task_track` |
| `mean_reward` / `score_100` | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.0 |
| 每题均值 | bottle_transfer 0.0 | 五题各 0.0 | 五题各 0.0 |
| `archive_sha256` | `5e1274ce…07ba4` | 同左 | 同左 |
| `source_sha256` | `3627ba43…a599f` | 同左 | 同左 |
| `result_sha256` | `0f7a9d3a0fd82e638f4d01c9fea57e106f654b4e4b1b072a2e00d7c5c13eea86` | `132a96764fbbd5d04d4ede08d29fb3326f051d6a32b22d7277c594af1f729db8` | `0e27d097535b2c0d0d0aa6b149007b1d2e5e4d72b1b06efda7be5009b0ece4cc` |

自检覆盖（`evidence/verify_results.py`，仅标准库）：

1. `result_sha256` 与规范 JSON 重算一致；`wait` / `result` 两次取回一致（本仓库保存的是 `wait` 版本，`result` 版本除文件名外内容相同）。
2. `evaluation_id`、`robot`、`scope`、`task_ids`、`planned_count`、`source_sha256`、`archive_sha256` 与接受回执逐项一致。
3. `idle.zip` 实际字节 SHA256 与回执 `archive_sha256` 一致。
4. smoke=4 / full=20 的计划数与有效数一致；每题 4 个不同 trial ID、全部 `state=scored`、`reward` 为 0 或 1。
5. 每题 `mean_reward` = 四次 reward 的算术均值；总 `mean_reward` = 题均值；`score_100` = 100×均值。
6. `state=scored`、`scoreIsFinal`、`scored`、`physical_evaluation`、`competition_ready=false`、`seed_randomizes_layout=false` 符合当前联调合同。

## 5. 遇到/需要注意的问题归纳

### 5.1 环境与客户端（本次实际遇到 ★）

| # | 类别 | 现象 | 原因 | 处理 / 建议 |
|---|---|---|---|---|
| 1 ★ | Windows 环境 | 按文档直接执行 `python3 lab_eval.py tasks` 会命中 Microsoft Store 占位程序（`WindowsApps\python3.exe`），不是真实解释器 | Windows 默认无 `python3` 命令别名 | 改用 `python`（本机 `D:\python\python310\python.exe`，3.10.11）或 `py -3`；命令其余参数不变 |
| 2 ★ | 打包哈希 | `pack` 输出的 `archive_sha256` 与工具包自带 `idle-submission.zip` 的哈希不同，一度怀疑打包不一致 | ZIP 成员时间戳等元数据不同，但 `source_sha256`（按路径排序的成员清单摘要）一致 | 正常现象。服务校验的是**实际上传 ZIP 字节**；以本次 `pack` 输出为准，不要拿示例包的 archive 哈希比对 |
| 3 ★ | 终端编码 | 在 Windows PowerShell 直接 `Get-Content` 读取 UTF-8 文档出现乱码（仅显示问题，不影响程序） | 控制台默认代码页（GBK）与 UTF-8 文件不一致 | 用 UTF-8 感知的工具/编辑器读取，或 `[Console]::OutputEncoding` 调整；CLI 输出本身正常 |
| 4 | 输出文件 | `pack/submit/wait/result` 的输出文件已存在时会直接报错 | 客户端用 `open('x')` 创建文件，拒绝覆盖 | 重取结果用新文件名（本次用 `*-result-copy.json`）；不要删除旧回执 |
| 5 | `--receipt` 语义 | `--receipt` 在 `submit` 是**写**回执，在 `wait/result` 是**只读**核对 | 同一参数名两种用途 | 按文档区分；`wait/result --receipt` 不一致会退出 1 且不保存结果 |
| 6 | 输出体积 | 每条 `result` 成功时向 stdout 打印完整结果 JSON（本次 single ~2.5 KB、full ~8 KB） | CLI 设计如此 | 脚本化时重定向 stdout；状态变化走 stderr，可用 stderr 做进度日志 |
| 7 | token 处理 | token 文件短（44 字节）；客户端要求读取后长度 ≥24；提供 `--token-file` 或 `LAB_EVAL_TOKEN_FILE` | 凭证安全设计 | 用绝对路径 `--token-file`（Windows 路径可直接用）；不要把 token 写进命令、日志、策略包或仓库 |

### 5.2 服务与流程

| # | 类别 | 现象 / 规则 | 影响 | 处理 / 建议 |
|---|---|---|---|---|
| 8 | 时区 | 回执与 `tasks` 使用 UTC（`accept_until=2026-10-26T04:00:00Z`），截止按北京时间 10-26 12:00 | 按本地时间判断会误判截止 | 换算后再排期：UTC+8；截止前入队不保证到期前跑完 |
| 9 | 队列配额 | 每个机器人同时只跑一个评测；团队最多 2 项未终结评测 | 两条 full 并行提交正好占满配额，无法再并行第三条 | 提交前先 `tasks` 看容量；容量满先等已有任务，不要重复提交催进度 |
| 10 | 运行时长 | 空策略 smoke 4 次约 4 分 41 秒；full 20 次约 23–24 分钟（含 provisioning） | 排队/等待时间不可压缩；策略动作越多越久 | 按 20–30 分钟量级预留 full；`wait --timeout 7200 --poll 10` 足够 |
| 11 | 状态机 | `queued → provisioning → running → verifying → scored`；终态还有 `requires_review`、`cancelled_before_start` | `queued`、HTTP 202、进程结束都不是最终成绩 | 只轮询同一 `evaluation_id`；`requires_review` 保留 ID 交组织者，不要改成 0 分 |
| 12 | 分数口径 | smoke 的 `score_100` 是单题均值×100（`single_task_smoke`）；full 才是 `five_task_track` 赛道分 | 把 smoke 当赛道分会误报 | 报告时保留 `score_scope`；full 的 `score_100 = 五题均值×100` |
| 13 | 公开身份 | `competition_ready=false`、`seed_randomizes_layout=false`，固定公开布局 | 当前分数不是正式隐藏集/榜单成绩 | 报告中明确"开发联调分"；不要当作官方榜单结果 |
| 14 | 空策略含义 | 空策略正常"观察一次 + 一个等待步 + finish"，物理 0 分 | 0 分只证明链路 | 不要把链路验收与算法能力混为一谈 |
| 15 | 上传不确定 | 若上传响应丢失，先 `lookup <idempotency-key>` 找回，同键同包同计划可幂等恢复 | 重复 POST 可能产生歧义 | 不要重新打包后复用旧键（同键不同包会 409 `IDEMPOTENCY_CONFLICT`） |
| 16 | 结果核对 | 不传 `--receipt` 时客户端不自动核对身份；结果字段里 `evaluation_id`、两处 SHA256、计划次数都必须手核 | 手工核对易漏 | 始终带 `--receipt`；本仓库 `verify_results.py` 提供独立复现 |
| 17 | 退出码 | 0=有效最终结果；2=未形成最终成绩/需复核；3=等待超时；1=请求/校验失败 | 0 分（分数）与退出码 0（流程成功）不是一回事 | 报告分数时同时报告退出码与 `state` |

### 5.3 本次未触发但值得知道

- 401 `UNAUTHORIZED`（token 错误）、429 `QUEUE_FULL` / `TEAM_QUEUE_FULL`、409 `RESULT_NOT_READY`、503 `WORKER_UNAVAILABLE` / `ADMISSION_WINDOW_CLOSED` 均未出现；未出现 `requires_review`。
- `wait` 超时只结束客户端等待，**不会取消服务端评测**，用同一 ID 继续查即可。
- 策略运行时的 `/tmp`、网络、CPU 限额只影响策略进程，不影响提交客户端；本报告不涉及策略调试。
- 结果 API 不返回策略 `/tmp` 文件、完整观测或私有接触证据，调试需依赖工具包公开样例与本地开发环境。

### 5.4 对工具/文档的小建议（非阻塞）

1. CLI 增加"输出文件已存在时 `--overwrite`/`--force`"或"输出到 `-` 直接打印"，减少 `-copy` 文件。
2. 文档在 Windows 段落注明用 `python`/`py -3`，并说明 `pack` 的 `archive_sha256` 会因 ZIP 元数据与示例包不同、应以 `source_sha256` 做内容一致性判断。
3. `tasks`/回执可附带北京时间字段或时区标注，降低截止时间误判。
4. 结果 JSON 较大，若提供 `--quiet`（只输出摘要）更利于自动化。

## 6. 复现方式

1. 解压组织者提供的 participant-kit，安装 Python 3.10+；准备组织者单独发放的 token 文件。
2. 按 §3 的命令执行（将 `<TOKEN_FILE>`、`<RUN>`、`<EVAL_ID>` 替换为实际值）；`service.json` 提供当前服务入口。
3. 结果文件放在独立目录后，执行：

```powershell
python evidence\verify_results.py <participant-kit 目录>
```

脚本会独立复核 `evidence/` 下全部回执/结果与 `idle.zip`，输出 `ALL CHECKS PASSED` 并以 0 退出。

## 7. 仓库文件

| 文件 | 说明 |
|---|---|
| `README.md` | 本报告 |
| `evidence/README.md` | 证据说明与复现方法 |
| `evidence/idle.zip` | 本次提交的冻结策略包（`archive_sha256=5e1274ce…07ba4`） |
| `evidence/franka-smoke-accepted.json` / `-result.json` | smoke 接受回执 / 最终结果 |
| `evidence/franka-full-accepted.json` / `-result.json` | franka full 接受回执 / 最终结果 |
| `evidence/dual_piper-full-accepted.json` / `-result.json` | dual_piper full 接受回执 / 最终结果 |
| `evidence/summary.json` | 机器可读汇总（ID、哈希、逐题 reward 与均值） |
| `evidence/verify_results.py` | 独立自检脚本（仅 Python 标准库） |

## 8. 边界声明

- 本轮为**邀请联调开发评测**，不是正式隐藏测试或排行榜成绩；`scoreIsFinal=true` 只表示本计划内分数完整，不表示正式赛封榜。
- 空策略 0 分不包含任何"任务成功"声明；五题操作策略仍需另行开发与验收。
- 本报告只使用服务公开返回字段与工具包公开文档，不包含裁判私有证据、对象真值或凭证。
