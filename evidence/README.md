# 证据说明

本目录保存本次邀请联调（`20261023-colleague-test-01`）的真实接受回执与最终结果，全部来自组织者服务的公开 REST 返回。

## 文件

| 文件 | 来源 | 说明 |
|---|---|---|
| `idle.zip` | `lab_eval.py pack examples/idle` | 实际上传的冻结策略包；`archive_sha256=5e1274ce60f5696edd1b6c47ac5e68bcaed6f33fc1fb2e743630d90312607ba4` |
| `franka-smoke-accepted.json` | `submit --scope smoke` 的接受回执（HTTP 202） | franka、`bottle_transfer`、4 次计划 |
| `franka-smoke-result.json` | `wait --receipt` 下载并校验的最终结果 | 4/4 有效，`single_task_smoke` |
| `franka-full-accepted.json` | `submit --scope full` 的接受回执 | franka、五题、20 次计划 |
| `franka-full-result.json` | 最终结果 | 20/20 有效，`five_task_track` |
| `dual_piper-full-accepted.json` | `submit --scope full` 的接受回执 | dual_piper、五题、20 次计划 |
| `dual_piper-full-result.json` | 最终结果 | 20/20 有效，`five_task_track` |
| `summary.json` | 本仓库汇总 | 3 次评测的 ID、哈希、逐题 reward 与均值 |
| `verify_results.py` | 本次编写 | 独立自检脚本（仅 Python 标准库），不需要组织者工具包 |

`*-result.json` 与当时 `result` 命令复取的文件内容完全一致，因此仓库不重复保存 `*-copy.json`。

## 离线自检

```powershell
python verify_results.py
# 输出 ALL CHECKS PASSED 并以 0 退出
```

自检内容：

1. 每个结果信封的 `result_sha256` = 对 `result` 做 UTF-8、键排序、无多余空格、不转义非 ASCII 的规范 JSON 后取 SHA256；
2. `evaluation_id`、`robot`、`scope`、`task_ids`、`planned_count`、`source_sha256`、`archive_sha256` 与接受回执逐项一致；
3. `idle.zip` 实际字节 SHA256 = 回执 `archive_sha256`；
4. smoke 计划 4、full 计划 20，`planned_count` = `scored_count`；每题 4 个不同 trial ID，全部 `state=scored`、`reward` 为 0 或 1；
5. 每题 `mean_reward` = 4 次 reward 的算术均值；总 `mean_reward` = 题均值；`score_100` = 100×均值；
6. `state=scored`、`scoreIsFinal`、`scored`、`physical_evaluation`、`competition_ready=false`、`seed_randomizes_layout=false` 符合当前联调合同。

## 注意

- 目录中不含 token、服务入口 URL、私有接触证据或裁判内部状态；`score` 字段来自组织者服务公开返回。
- 这些文件是**开发联调**证据，不能解释为正式比赛成绩；空策略 0 分只证明链路有效。
