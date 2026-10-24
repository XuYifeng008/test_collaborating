# 离线协议测试结果（fixtures / Adapter / 频率 / finish / C07 去皮）

- 生成时间：2026-10-24T09:28:11Z（UTC）/ 2026-10-24T17:28:11.525936+08:00（本地）
- 套件状态：**pass**
- 通过 / 失败 / 错误 / 跳过：17 / 0 / 0 / 0
- 总耗时：34.59s

## 环境与输入

- 公开包根目录：`E:\dev\agents\lark-working\inbox\1024-test\自主实验赛道选手公开包`
- 策略目录：`E:\dev\agents\lark-working\deliverables\2026-10-24-nine-task\src\my-policy`（入口 `policy.py`，存在=True）
- Python：3.10.11；平台：Windows-10-10.0.26200-SP0
- NumPy：1.26.4
- 真实公开样例：4 份；协议合成用例：14 份

> **合成标记**：`synthetic=true` 的用例是“同一 wave/robot 真实样例派生、仅替换 task_id”的协议形状用例，不是真实记录数据；C07 的感知检测与天平回执是测试桩，不声称物理成功或真实测量。

## 用例结果总览

| 测试 | 类别 | 状态 | 检查(通过/失败/警告) | 耗时 | 说明 |
| --- | --- | --- | --- | ---: | --- |
| `fixtures:integrity` | fixtures | **PASS** | 61/0/0 | 0.00s | real vs synthetic is distinguished in fixtures + report; synthetic never presented as real |
| `adapter:canonical_projection` | fixtures | **PASS** | 698/0/0 | 0.05s |  |
| `protocol:frequency_semantics` | protocol | **PASS** | 72/0/0 | 0.02s |  |
| `protocol:joint_order_mapping` | protocol | **PASS** | 117/0/0 | 0.02s |  |
| `adapter:action_boundary` | protocol | **PASS** | 67/0/0 | 0.01s |  |
| `driver:self_check` | driver | **PASS** | 36/0/0 | 0.50s |  |
| `policy:submission_source` | policy | **PASS** | 15/0/0 | 0.08s |  |
| `real:wave1:franka:bottle_transfer` | real_fixture_episode | **PASS** | 14/0/0 | 0.26s | public fixture has no RGB payloads; expected policy path is 'perception unavailable -> safe retract + hold + finish'.... |
| `real:wave1:piper-dual:bottle_transfer` | real_fixture_episode | **PASS** | 14/0/0 | 0.40s | public fixture has no RGB payloads; expected policy path is 'perception unavailable -> safe retract + hold + finish'.... |
| `real:wave2:piper-dual:C07` | real_fixture_episode | **PASS** | 20/0/0 | 0.33s | public fixture has no RGB payloads; expected policy path is 'perception unavailable -> safe retract + hold + finish'.... |
| `real:wave2:franka:C02` | real_fixture_episode | **PASS** | 15/0/0 | 0.24s | public fixture has no RGB payloads; expected policy path is 'perception unavailable -> safe retract + hold + finish'.... |
| `c07:nominal_tare_state_machine` | c07_state_machine | **PASS** | 29/0/0 | 4.81s | SYNTHETIC perception stub injected into policy.perceive (no real camera); scripted balance receipts (FakeBalance) are... |
| `c07:abnormal_unstable_receipt` | c07_state_machine | **PASS** | 22/0/0 | 4.04s | SYNTHETIC perception stub injected into policy.perceive (no real camera); scripted balance receipts (FakeBalance) are... |
| `c07:abnormal_missing_receipt` | c07_state_machine | **PASS** | 22/0/0 | 4.10s | SYNTHETIC perception stub injected into policy.perceive (no real camera); scripted balance receipts (FakeBalance) are... |
| `c07:persistent_abnormal_safe_abort` | c07_state_machine | **PASS** | 22/0/0 | 4.93s | SYNTHETIC perception stub injected into policy.perceive (no real camera); scripted balance receipts (FakeBalance) are... |
| `synthetic:wave1_smoke` | synthetic_smoke | **PASS** | 32/0/0 | 8.85s |  |
| `synthetic:wave2_smoke` | synthetic_smoke | **PASS** | 24/0/0 | 5.73s |  |

## 失败检查明细

- 无失败检查。

## 过程性缺陷记录（发现→报告→策略作者修复→本轮复测）

### `policy:wave2-finish-hold-truncated` — found -> reported -> fixed by policy author -> re-verified clean

- 位置：src/my-policy/policy.py _finish_tick
- 现象：wave2 safe-abort episodes finished after only 120 hold steps (1.0 s) instead of the required >=1.2 s; the last 30-step hold segment was dropped because finish was returned before the remaining hold was issued.
- 修复前证据：
  - real:wave2:piper-dual:C07 terminal_hold_steps=120 < required 144
  - real:wave2:franka:C02 terminal_hold_steps=120 < required 144
- 修复后本轮验证：
  - real:wave2:piper-dual:C07 terminal_hold_steps=150 (1.25 s)
  - real:wave2:franka:C02 terminal_hold_steps=150 (1.25 s)
  - both cases deterministic across two runs (identical action digests)

> 依据任务约定，测试只报告缺陷、不修改 `src/`；上述缺陷由策略作者修复后，本轮全量复测通过。

## 回合统计（真实样例与合成 smoke）

| 测试 / 回合 | 用例 | synthetic | finish | cap_reason | calls | step动作 | 物理步 | 保持步 | instrument(read/tare) | 违规 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `driver:self_check` / positive_control_minimal_policy | `real:wave1:franka:bottle_transfer` | False | True | finish | 2 | 1 | 721 | 1 |  | - |
| `real:wave1:franka:bottle_transfer` / run2 | `real:wave1:franka:bottle_transfer` | False | True | finish | 26 | 25 | 930 | 0 |  | - |
| `real:wave1:franka:bottle_transfer` / run1 | `real:wave1:franka:bottle_transfer` | False | True | finish | 26 | 25 | 930 | 0 |  | - |
| `real:wave1:piper-dual:bottle_transfer` / run2 | `real:wave1:piper-dual:bottle_transfer` | False | True | finish | 32 | 31 | 980 | 0 |  | - |
| `real:wave1:piper-dual:bottle_transfer` / run1 | `real:wave1:piper-dual:bottle_transfer` | False | True | finish | 32 | 31 | 980 | 0 |  | - |
| `real:wave2:piper-dual:C07` / run2 | `real:wave2:piper-dual:C07` | False | True | finish | 31 | 30 | 396 | 150 | 0/0 | - |
| `real:wave2:piper-dual:C07` / run1 | `real:wave2:piper-dual:C07` | False | True | finish | 31 | 30 | 396 | 150 | 0/0 | - |
| `real:wave2:franka:C02` / run2 | `real:wave2:franka:C02` | False | True | finish | 23 | 22 | 314 | 150 |  | - |
| `real:wave2:franka:C02` / run1 | `real:wave2:franka:C02` | False | True | finish | 23 | 22 | 314 | 150 |  | - |
| `c07:nominal_tare_state_machine` / run2 | `real:wave2:piper-dual:C07` | False | True | finish | 150 | 139 | 1848 | 450 | 9/1 | - |
| `c07:nominal_tare_state_machine` / run1 | `real:wave2:piper-dual:C07` | False | True | finish | 150 | 139 | 1848 | 450 | 9/1 | - |
| `c07:abnormal_unstable_receipt` / run1 | `real:wave2:piper-dual:C07` | False | True | finish | 150 | 139 | 1848 | 450 | 9/1 | - |
| `c07:abnormal_missing_receipt` / run1 | `real:wave2:piper-dual:C07` | False | True | finish | 150 | 139 | 1848 | 450 | 9/1 | - |
| `c07:persistent_abnormal_safe_abort` / run1 | `real:wave2:piper-dual:C07` | False | True | finish | 185 | 157 | 2928 | 450 | 26/1 | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:franka:beaker_place` | True | True | finish | 26 | 25 | 930 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:franka:balance_load` | True | True | finish | 26 | 25 | 930 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:franka:stirrer_knob` | True | True | finish | 26 | 25 | 930 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:franka:tube_insert` | True | True | finish | 26 | 25 | 930 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:piper-dual:beaker_place` | True | True | finish | 32 | 31 | 980 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:piper-dual:balance_load` | True | True | finish | 32 | 31 | 980 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:piper-dual:stirrer_knob` | True | True | finish | 32 | 31 | 980 | 0 |  | - |
| `synthetic:wave1_smoke` / smoke | `synthetic:wave1:piper-dual:tube_insert` | True | True | finish | 32 | 31 | 980 | 0 |  | - |
| `synthetic:wave2_smoke` / smoke | `synthetic:wave2:franka:C01` | True | True | finish | 23 | 22 | 314 | 150 |  | - |
| `synthetic:wave2_smoke` / smoke | `synthetic:wave2:franka:C04` | True | True | finish | 23 | 22 | 314 | 150 |  | - |
| `synthetic:wave2_smoke` / smoke | `synthetic:wave2:franka:C07` | True | True | finish | 24 | 23 | 317 | 150 | 0/0 | - |
| `synthetic:wave2_smoke` / smoke | `synthetic:wave2:piper-dual:C01` | True | True | finish | 29 | 28 | 364 | 150 |  | - |
| `synthetic:wave2_smoke` / smoke | `synthetic:wave2:piper-dual:C02` | True | True | finish | 29 | 28 | 364 | 150 |  | - |
| `synthetic:wave2_smoke` / smoke | `synthetic:wave2:piper-dual:C04` | True | True | finish | 29 | 28 | 364 | 150 |  | - |

## C07 去皮状态机（合成桩）

| 测试 | 回合 | 空质量桩模式 | 有效 tare | tare 尝试 | 二次 tare | tare 后 read | 最终 read 净质量 g |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `real:wave2:piper-dual:C07` | run2 | nominal | 0 | 0 | 0 | 0 | - |
| `real:wave2:piper-dual:C07` | run1 | nominal | 0 | 0 | 0 | 0 | - |
| `c07:nominal_tare_state_machine` | run2 | nominal | 1 | 1 | 0 | 7 | 10.100 |
| `c07:nominal_tare_state_machine` | run1 | nominal | 1 | 1 | 0 | 7 | 10.100 |
| `c07:abnormal_unstable_receipt` | run1 | abnormal_unstable | 1 | 1 | 0 | 6 | 10.100 |
| `c07:abnormal_missing_receipt` | run1 | abnormal_missing | 1 | 1 | 0 | 6 | 10.100 |
| `c07:persistent_abnormal_safe_abort` | run1 | abnormal_persistent | 1 | 1 | 0 | 0 | - |
| `synthetic:wave2_smoke` | smoke | nominal | 0 | 0 | 0 | 0 | - |

> 表中 `real:wave2:piper-dual:C07` 行是**未注入感知**的安全中止路径（无 tare）；其余 C07 行注入合成感知桩与脚本化天平回执，只验证状态机/协议，不是物理成功或真实测量。

## 真实公开样例（来源与哈希）

| wave | robot | task | source_release | instruction sha256 (original) |
| --- | --- | --- | --- | --- |
| wave1 | franka | bottle_transfer | wave1-public-kit-20261023 | `c4c9888e21f0886b13e0113049d1fd4bc46998ce64aa0ac8ff825f8fc6b23507` |
| wave1 | piper-dual | bottle_transfer | wave1-public-kit-20261023 | `05e15fdef967ce0fe9adc95ba2dbe5a43a9f1d6b9d0caea6177994aa0acb6622` |
| wave2 | piper-dual | C07 | wave2-full-r23-20261024 | `22f0f603a3f4af78edb3a7d0c45603c1999c0ab712756571024d0fd406d3bc8a` |
| wave2 | franka | C02 | wave2-full-r23-20261024 | `d29b1a840cc302ba418c11afd1c64965582c0bf2dc32cce32544968bbf85d0b7` |

## 协议合成用例（synthetic=True，非真实数据）

- `synthetic:wave1:franka:beaker_place`（derived_from=real:wave1:franka:bottle_transfer）
- `synthetic:wave1:franka:balance_load`（derived_from=real:wave1:franka:bottle_transfer）
- `synthetic:wave1:franka:stirrer_knob`（derived_from=real:wave1:franka:bottle_transfer）
- `synthetic:wave1:franka:tube_insert`（derived_from=real:wave1:franka:bottle_transfer）
- `synthetic:wave1:piper-dual:beaker_place`（derived_from=real:wave1:piper-dual:bottle_transfer）
- `synthetic:wave1:piper-dual:balance_load`（derived_from=real:wave1:piper-dual:bottle_transfer）
- `synthetic:wave1:piper-dual:stirrer_knob`（derived_from=real:wave1:piper-dual:bottle_transfer）
- `synthetic:wave1:piper-dual:tube_insert`（derived_from=real:wave1:piper-dual:bottle_transfer）
- `synthetic:wave2:franka:C01`（derived_from=real:wave2:franka:C02）
- `synthetic:wave2:franka:C04`（derived_from=real:wave2:franka:C02）
- `synthetic:wave2:franka:C07`（derived_from=real:wave2:franka:C02）
- `synthetic:wave2:piper-dual:C01`（derived_from=real:wave2:piper-dual:C07）
- `synthetic:wave2:piper-dual:C02`（derived_from=real:wave2:piper-dual:C07）
- `synthetic:wave2:piper-dual:C04`（derived_from=real:wave2:piper-dual:C07）

## 已知限制（必须随结果一起阅读）

- 本套件是**协议测试**，不是仿真器：无接触/物体/液体物理、无 RGB 相机、无私有判分真值。
- 观测回写是**运动学 mock**：关节/夹爪回显最近一次命令，TCP 位姿用公开 `robot_kinematics` 前向运动学重算；不声称物理正确性。
- 真实 4 份 fixture 的图片 payload 已被公开包移除，策略预期走“感知不可用 → 安全收回 + 保持 + finish”路径；测试只断言协议合法、预算内、finish 语义、确定性与安全中止，不判任务成败。
- C07 的 balance 回执与 perception 检测为脚本化测试桩（含人为稳定延迟/出液速率）；只验证“放稳→读稳定→仅一次去皮→按净质量停倒→回源→保持→finish”的协议状态机。
- 关节顺序/限位来自公开 instruction；策略源码静态频率扫描只把“秒数*240”类换算式标为失败，裸常量仅警告，最终以动态 act 行为为准。

## 结论

- 全部已执行用例通过（17 passed，0 failed）。未发现未修复的策略缺陷或协议不匹配。
- 测试过程中发现并报告的 1 个策略缺陷已由策略作者修复，本轮全量复测通过（见上方“过程性缺陷记录”）。

