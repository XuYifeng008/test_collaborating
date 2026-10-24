# 公开包身份与合同核验报告

- 任务：`task-1` 公开包身份与合同核验（哈希/规则/运行档/fixtures/Adapter）
- 公开包：`inbox/1024-test/自主实验赛道选手公开包`（只读，未联网、未提交评测、未读 token）
- 生成时间（UTC）：`2026-10-24T09:20:17Z`
- 脚本：`verify_contracts.py`，SHA256 `ebcbd84eefc4546167fd5c1dba5eef3db2f63a5325a97fae86255c53815eea50`
- 运行环境：Python 3.10.11 / Windows-10-10.0.26200-SP0
- 本次退出码：0（全部必检通过）
- 复现：在本目录执行 `python verify_contracts.py`（脚本自行重建 JSON 与本报告；追加 `--timestamp 2026-10-24T00:00:00Z` 可逐字节复现同一 JSON）

## 结论

**公开包身份自洽：清单、release 合同哈希、运行档绑定、Adapter 协议与 4 份真实样例全部符合。**

| 指标 | 数量 |
| --- | ---: |
| 检查项总数 | 930 |
| 通过 | 915 |
| 不符合（问题） | 0 |
| 记录项（info） | 15 |

| 类别 | 检查 | 通过 | 问题 | 记录 |
| --- | ---: | ---: | ---: | ---: |
| A. PUBLIC-MANIFEST 文件身份 | 44 | 41 | 0 | 3 |
| B. release.json ↔ contracts 合同哈希 | 58 | 55 | 0 | 3 |
| C. 运行档冻结清单绑定 | 64 | 64 | 0 | 0 |
| D. 机器人/模型/规则身份事实 | 166 | 163 | 0 | 3 |
| E. Adapter × 真实 fixtures 协议与动作矩阵 | 495 | 492 | 0 | 3 |
| F. 文档与合同交叉一致性 | 103 | 100 | 0 | 3 |

## 关键身份事实

| 项 | 值 |
| --- | --- |
| 规则身份 | `lab-nine-20261024-v1`（rules version 1.0.0） |
| 发布版本 | `1.0.0`（editorial_revision=3） |
| 运行档 | profile_id=`lab-nine-image-model-v1` |
| 唯一模型 | `rynnbrain-1.1-2b-local` → `Alibaba-DAMO-Academy/RynnBrain1.1-2B`@`36069aa841fc` |
| 模型权重 SHA256 | `2819d84441c27c18c403c1302f60ff1ba2c9cfcdc989657bf6589e8cd11a7e6d` |
| 机器人 | franka：臂 `['arm']`，7 关节；piper-dual：臂 `['left', 'right']`，每臂 6 关节 |
| wave2 piper 原生→统一 | `arm`→`left`，`right`→`right`（wave1 为 `left/right` 不变） |
| 频率/结束 | wave1=240Hz、finish +720 步（3.0s）；wave2=120Hz、finish +0 步 |
| 36 槽计分 | `100 * sum(task_success_count / 4 for each of 9 tasks) / 9`；分母 36；显示 6 位；中间舍入=False |
| platform | playground_integrated=False / official_score_writeback_verified=False / competition_ready=False / challenge_ids=None |
| release 补充 | live_nine_task_service_deployed=False / new_runtime_native_full36_verified=False / external_model_api_qualified=False |
| SDK | `lab_sdk.__version__`=2.0.0，冻结成员 6 个 |
| 夹爪范围 m | wave1 franka=[0, 0.08]、piper-dual=[0, 0.08]；wave2 franka=[0, 0.08]、piper-dual=[0, 0.1] |
| 动作合同 | steps=[1, 120]；观察暂停物理=True；推理暂停物理=True；墙钟继续=True |
| 预算 | wave1：simulation=180.0/180.0/360.0/120.0/120.0 s、API=2500/2500/5000/1200/1200、CPU 120s/墙钟 600s、startup 900s；wave2：simulation=1200 s、max_physics_steps=144000、API=10000（唯一变更请求）、CPU 120s/墙钟 3600s、startup 900s |

## 关键 SHA 对照

| 身份 | 声明值（release） | 实测值 | 结果 |
| --- | --- | --- | --- |
| contracts/rules-v1.json 规范 JSON SHA | `e65b8edb7afc1d2ee901e2b5589f372028def43c319e66bb4852e7754c8dbc11` | `e65b8edb7afc1d2ee901e2b5589f372028def43c319e66bb4852e7754c8dbc11` | 一致 |
| contracts/runtime-profile.json 规范 JSON SHA | `b32b478e6b0051e53fb774fc3b52b666352c8c427d3e6ec3e1994d7b41341639` | `b32b478e6b0051e53fb774fc3b52b666352c8c427d3e6ec3e1994d7b41341639` | 一致 |
| contracts/configuration-template.json 规范 JSON SHA | `0e50177954035a578741140edf0bd68a7ac254e807b739fff3a89176e12894d2` | `0e50177954035a578741140edf0bd68a7ac254e807b739fff3a89176e12894d2` | 一致 |
| lab_sdk 六成员 source hash（ASCII 清单） | `8bfc68398c0b4bde307c0a00e838baf3ed1db92504f1b27ca87518e6ed7f5cc8` | `8bfc68398c0b4bde307c0a00e838baf3ed1db92504f1b27ca87518e6ed7f5cc8` | 一致 |
| runtime/model-registry.json 原始字节 SHA | `9d60ca7505d1b3249f4ddd03b275d1e9b8009caca908dcdf9fee679d930db4e0` | `9d60ca7505d1b3249f4ddd03b275d1e9b8009caca908dcdf9fee679d930db4e0` | 一致 |
| runtime/wheels.lock.json 原始字节 SHA | `dd495064d834c9e7ed661a9bd457c33bba001c2831300188b9f552459ec1116f` | `dd495064d834c9e7ed661a9bd457c33bba001c2831300188b9f552459ec1116f` | 一致 |
| PUBLIC-MANIFEST.json 文件自身 SHA（清单自排除） | `(not listed)` | `a2ea26c9d9386f36f74150136f600ee0cbca2a894f135a84c73a9e1832bf37de` | 自排除（不清单，不比较） |

## PUBLIC-MANIFEST 文件身份

- 清单覆盖 33 个文件，逐文件 bytes/sha256 匹配 **33/33**，不符 0 个。
- 包内实际文件 34 个；除清单外未发现其它发布内容文件（`PUBLIC-MANIFEST.json` 自排除属预期）。
- 运行缓存：`lab_sdk/__pycache__/` 下存在 5 个 `.pyc`（由在包内直接 `import lab_sdk` 的进程产生，非发布内容，不计入清单身份）：`lab_sdk/__pycache__/__init__.cpython-310.pyc`, `lab_sdk/__pycache__/adapters.cpython-310.pyc`, `lab_sdk/__pycache__/client.cpython-310.pyc`, `lab_sdk/__pycache__/models.cpython-310.pyc`, `lab_sdk/__pycache__/packaging.cpython-310.pyc`。
- 清单路径排序=是；重复路径=无；符号链接=无。

## fixtures × Adapter（4 份真实公开样例）

| # | wave | robot | task | 内部检查 | 失败 | 结果 |
| ---: | --- | --- | --- | ---: | ---: | --- |
| 0 | wave1 | franka | `bottle_transfer` | 112 | 0 | 通过 |
| 1 | wave1 | piper-dual | `bottle_transfer` | 123 | 0 | 通过 |
| 2 | wave2 | piper-dual | `C07` | 130 | 0 | 通过 |
| 3 | wave2 | franka | `C02` | 112 | 0 | 通过 |

每份样例核验：schema→wave 推断、原生 robot_profile 归一、原生/统一臂键映射、`physics.step_seconds/frequency_hz`、`finish.extra_physics_steps`、每臂关节数量与顺序、夹爪范围、kinematics 限位、observation 臂名映射与 finished 推导，以及动作合法/非法矩阵（关节数、steps 1–120、非有限数、越限、未知字段/臂、finish 精确 dict、instrument 仅 wave2 C07）。

### Case 0 · wave1 / franka / `bottle_transfer`

- 内部检查：通过 112 / 失败 0
- 动作矩阵：合法动作通过 8/8，非法动作被拒绝 24/24
- 统一指令：`lab-instruction/v2`；step_seconds=0.004166666666666667（240 Hz）；`finish.extra_physics_steps`=720；每动作最大步数=120；instrument 允许=否
- 臂映射：原生 `['arm']` → 统一 `['arm']`；observation 原生 `['arm']` → 统一 `['arm']`
- 每臂合同：`arm`：7 关节 ['panda_joint1', 'panda_joint2', 'panda_joint3', 'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7']、夹爪范围 [0.0, 0.08] m
- 通过项分组（组名 通过/总数）：action 40/40、adapter 7/7、fixture 1/1、guard 10/10、instruction 34/34、observation 13/13、provenance 5/5、robot_profile_native 1/1、wave_matches 1/1
- provenance：source_release=`wave1-public-kit-20261023`，原始 instruction/observation SHA 已记录（原件不在包内，不可重算）

### Case 1 · wave1 / piper-dual / `bottle_transfer`

- 内部检查：通过 123 / 失败 0
- 动作矩阵：合法动作通过 9/9，非法动作被拒绝 24/24
- 统一指令：`lab-instruction/v2`；step_seconds=0.004166666666666667（240 Hz）；`finish.extra_physics_steps`=720；每动作最大步数=120；instrument 允许=否
- 臂映射：原生 `['left', 'right']` → 统一 `['left', 'right']`；observation 原生 `['left', 'right']` → 统一 `['left', 'right']`
- 每臂合同：`left`：6 关节 ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']、夹爪范围 [0.0, 0.08] m；`right`：6 关节 ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']、夹爪范围 [0.0, 0.08] m
- 通过项分组（组名 通过/总数）：action 42/42、adapter 7/7、fixture 1/1、guard 10/10、instruction 42/42、observation 14/14、provenance 5/5、robot_profile_native 1/1、wave_matches 1/1
- provenance：source_release=`wave1-public-kit-20261023`，原始 instruction/observation SHA 已记录（原件不在包内，不可重算）

### Case 2 · wave2 / piper-dual / `C07`

- 内部检查：通过 130 / 失败 0
- 动作矩阵：合法动作通过 11/11，非法动作被拒绝 27/27
- 统一指令：`lab-instruction/v2`；step_seconds=0.008333333333333333（120 Hz）；`finish.extra_physics_steps`=0；每动作最大步数=120；instrument 允许=是（wave2 C07）
- 臂映射：原生 `['arm', 'right']` → 统一 `['left', 'right']`；observation 原生 `['arm', 'right']` → 统一 `['left', 'right']`
- 每臂合同：`left`：6 关节 ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']、夹爪范围 [0.0, 0.1] m；`right`：6 关节 ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']、夹爪范围 [0.0, 0.1] m
- 通过项分组（组名 通过/总数）：action 49/49、adapter 7/7、fixture 1/1、guard 11/11、instruction 41/41、observation 14/14、provenance 5/5、robot_profile_native 1/1、wave_matches 1/1
- provenance：source_release=`wave2-full-r23-20261024`，原始 instruction/observation SHA 已记录（原件不在包内，不可重算）

### Case 3 · wave2 / franka / `C02`

- 内部检查：通过 112 / 失败 0
- 动作矩阵：合法动作通过 8/8，非法动作被拒绝 24/24
- 统一指令：`lab-instruction/v2`；step_seconds=0.008333333333333333（120 Hz）；`finish.extra_physics_steps`=0；每动作最大步数=120；instrument 允许=否
- 臂映射：原生 `['arm']` → 统一 `['arm']`；observation 原生 `['arm']` → 统一 `['arm']`
- 每臂合同：`arm`：7 关节 ['panda_joint1', 'panda_joint2', 'panda_joint3', 'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7']、夹爪范围 [0.0, 0.08] m
- 通过项分组（组名 通过/总数）：action 40/40、adapter 7/7、fixture 1/1、guard 11/11、instruction 33/33、observation 13/13、provenance 5/5、robot_profile_native 1/1、wave_matches 1/1
- provenance：source_release=`wave2-full-r23-20261024`，原始 instruction/observation SHA 已记录（原件不在包内，不可重算）

## 问题清单

无。所有必检合同/身份项均符合；未发现哈希或文档不一致。

## 无法从公开包独立核验的声明（如实记录）

- release.runtime_qualification 中的 runtime_source_archive_sha256 / runtime_manifest_sha256 / verification.test_log_sha256 指向未随公开包发布的归档、清单或测试日志，无法在包内独立复核，仅做格式与自洽检查。
- examples/sdk-fixtures.json 与 sdk-public-image.json 的 provenance.*_sha256_original 对应移除平台身份与图像 payload 前的原始记录；公开包不含原件，无法重算原始 SHA（仅验证格式、投影说明与来源一致性）。
- 本核验仅覆盖公开包的静态合同与 lab_sdk.adapters 协议行为，不包含真实物理仿真、九题评测、Isaac/GPU 运行、平台 Challenge/Attempt 接入或分数回写（release 明确 competition_ready=false）。
- 无法证明当前工作副本与冻结发布归档（frozen-source-003）逐字相同；只能证明工作副本中 rules/runtime-profile/configuration 规范 JSON 与 SDK source hash 等于 release.json 声明值。
- 真实公开样例只有 4 份：wave1 仅 bottle_transfer（两机器人），wave2 franka=C02、piper-dual=C07；9 题中仅 3 题有真实协议样例，其余任务仅由 rules/文档覆盖。
- wheels.lock 的下载 URL 与 wheel 字节未做网络/本地校验（任务禁用网络，且包内不含 wheel），仅核验记录格式、requirements 锁一致性与 profile 绑定 SHA。
- 公开包 lab_sdk/ 下存在 Python 字节码缓存文件（__pycache__/*.pyc），由在包内直接 import lab_sdk 的进程产生，不属 PUBLIC-MANIFEST 发布内容；本脚本已设置 sys.dont_write_bytecode=True，运行时不写缓存。如需与清单文件树逐字一致，请在无并发进程的干净副本上复核。

## 复现

```text
cd deliverables/2026-10-24-nine-task/evidence/contracts
python verify_contracts.py
```

退出码：0=全部必检通过；1=发现不一致（见问题清单）；2=脚本或输入错误。
