# nine-task-policy-001 · 九题公开观测策略

- 提交协议：`lab-submission/v2` / `lab-policy-v2`，入口 `policy.py`，`Policy()` 无参构造，
  `reset(instruction)` / `act(observation)`。
- 规则版本：`lab-nine-20261024-v1`（九题 × 4 次重复 = 36 槽，Franka 与双 PiPER 分榜）。
- 运行档：`lab-nine-image-model-v1`（Linux CPython 3.10，NumPy 1.26.4 / Pillow 11.3.0 /
  opencv-python-headless 4.11.0.86）。
- 模型声明：**本策略不发起任何模型推理**。本轮唯一获准模型为
  `rynnbrain-1.1-2b-local`（Alibaba-DAMO-Academy/RynnBrain1.1-2B，revision
  `36069aa841fc58f500d307316cbfdf379777ce8a`，权重 SHA256
  `2819d84441c27c18c403c1302f60ff1ba2c9cfcdc989657bf6589e8cd11a7e6d`），
  其运行资格与冻结依赖见 `runtime/model-registry.json` 与 `contracts/runtime-profile.json`；
  本包不携带模型权重、凭证或外部网络访问，`LAB_MODEL_SOCKET`/`LAB_MODEL_TOKEN` 均不读取。
  因此完整计分时绑定的模型身份与运行档摘要仍由平台从提交的
  `runtime_profile_sha256`/`configuration_sha256` 反查，而不是由策略自报。

## 文件

| 文件 | 说明 |
|---|---|
| `submission.json` | v2 提交清单（submission_id / interface / entrypoint） |
| `policy.py` | 入口：协议解析、预算、动作校验、两波 finish 语义、C07 仪器动作 |
| `kinematics.py` | 只用公开 `robot_kinematics` 的 FK / 阻尼最小二乘 IK + 公开关节限位 |
| `vision.py` | 只解码公开 PNG 的 RGB 感知（颜色块、量筒液面、亮/暗目标） |
| `skills.py` | 九个任务的状态机与运动原语（生成器，一次 act 产出一个动作） |

## 只使用公开观测

- 指令：`task_id`、`backend_wave`、`arms`（关节名/顺序/数量/夹爪范围）、
  `robot_kinematics`（基座位姿、关节 `local0`/`local1`、轴、TCP 偏移、限位）、
  `physics.step_seconds/frequency_hz/maximum_steps_per_action`、`finish.extra_physics_steps`、
  `budget`、`task_geometry_manual`、`visual_measurement`、`instruments` 等公开字段。
- 观测：`simulation_time_s`、`proprioception`（关节位置/速度/限位、实测 TCP、夹爪开口）、
  `images`（相机 ID 以回合返回为准）、`last_instrument_result`、公开仪器反馈。
- **不读取**：私有裁判状态、私有接触真值、物体真实位姿、成功标记，也不直接改物体/液量/仪器真值。

## 机器人、频率、结束行为

- 臂与关节顺序完全取自指令：Franka `arm`（7 关节），双 PiPER 统一 `left`/`right`（各 6 关节；
  第二波原生 `arm` 在 SDK 适配层映射为 `left`，策略不假设另一机器人维度）。
- 物理频率只从 `instruction.physics.step_seconds` / `frequency_hz` 读取（前五题 1/240 s、
  后四题 1/120 s），动作 `steps` 只取 1–120 的整数，不把秒数换算成另一波固定步数。
- `finish` 语义：
  - 第一波（`extra_physics_steps=720`）：策略发出精确 `{"finish": true}`，由后端保持当前目标
    并推进 720 个物理步；策略不自行补步。
  - 第二波（`extra_physics_steps=0`）：策略在 finish 前自行用保持动作推进 ≥1.25 s 的物理步
    （120 Hz 即 ≥150 步），再发 `{"finish": true}`；不把 finish 当物理推进。
- 两波预算分别处理：第一波读 `budget.remaining_*` 预留 finish；第二波按公开上限自行累计
  （每回合 1200 s × 120 Hz = 144000 物理步、10000 次唯一变更请求）。

## C07 去皮流程

1. 空接收杯上秤盘 → 释放 → 同臂撤离（≥30 mm 的移动）。
2. 等待 ≥1.4 s 物理步后调用 `competition_balance.read`；只有 `ok` 且 `stable`/`STABLE`
   的读数才算有效，连续 ≥2 次有效 stable 读后才调用一次 `tare`。
3. **有效去皮后绝不再改去皮版本**：`tare` 只发一次；若回执无效/缺失，不把旧质量当有效，
   走安全收尾而不是重复改变去皮版本。
4. 持源杯、倾角 ≥40°、对准接收器出液；每 0.5 s 物理步后 `read` 一次净质量，
   达到 10±0.5 g 后回正。
5. 源杯回位、释放、撤离；终态保持 ≥1 s 并复读确认；`instrument` 动作与机械臂动作严格分开。

## 已知验证边界（诚实声明）

公开包只提供协议样例（真实指令/观测片段，去掉图像）与受控模型/打包工具，**不包含九题
仿真器、裁判或资格服务**。本目录中的运动学/感知/任务技能只经过：

1. 真实公开 fixture 的协议级回归（4 例，无图像 → 感知不可用 → 安全收尾）；
2. 公开 kinematic 数据的 FK 自一致与 IK 闭合检查；
3. 用「运动学 mock + 合成感知 + 合成天平回执」跑通 C07 去皮/定量状态机（明确标注非物理）。

因此本策略**不声明任何任务成功、分数或物理可用性**。物理标定与官能验收必须在题目
正式入口提供的资格环境中完成。
