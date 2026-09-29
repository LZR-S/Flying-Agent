# Tello SDK 对齐配置

当前 v1 使用 `tello-sdk-2-basic` 配置。适配范围是 Tello SDK 2.0 的基础指令子集；提供 Webots 与 Tello 两个后端；Tello 接入已做离线故障验证，尚未完成真机飞行验收。

## 模型动作契约

每次 `act` 只执行一个动作，`value` 必须是整数。未保留旧版米制参数或 `rotate_cw` 别名，避免单位歧义。

| kind | value | 对应 SDK 文本 |
| --- | --- | --- |
| forward / back / left / right / up / down | 20–500 厘米 | `forward 40` 等 |
| cw / ccw | 1–360 度 | `cw 90` |
| speed | 10–100 cm/s | `speed 50` |
| takeoff / land / stop | 0，或省略 | 同名指令 |
| hold | 0–30 秒 | 本地等待，期间运行层保活；不是 SDK 指令 |

```json
{"tool":"act","arguments":{"kind":"left","value":40},"based_on_frame_id":"frame_000042","note":"调整机位"}
```

`stop` 表示停止移动并悬停，不是 `emergency` 停桨。没有向模型开放翻滚、`go/curve`、Mission Pad、任意 RC 或停桨指令。

`completed` 不向模型承诺实测位移精度。Webots 以 PID 容差判断移动完成；Tello 的移动与速度设置以 SDK 应答判断。真机降落另需新鲜、稳定的地面遥测，不能仅凭 `ok` 宣布落地。结果未知时禁止重发移动，也不允许模型继续普通飞行。

真机命令在主线程通过 `send_command_without_return` 单次发送，逐 tick 消费应答，没有后台命令线程。SDK 设置 `retry_count=1`，初始化命令同样不重试。`stop` 发送 SDK `stop`，正常应答后还需后续新鲜静止遥测才报告完成；空闲保活才发送零速 RC。UDP 应答没有命令 ID，发生超时、中断或缺失降落 ACK 后，会锁住本轮应答通道；恢复降落忽略 ACK，只用遥测确认。`close` 和 SDK 析构不隐式降落，避免未记录的重复动作。

地面判据要求不同的新遥测样本覆盖至少 0.5 秒：`h` 为 0–10 cm、有效 ToF 为 0–20 cm（不含 0）、三个速度分量绝对值不超过 5 cm/s、横滚与俯仰绝对值不超过 10°。样本过期或间隔超过 1 秒时重置确认。起飞指令一旦派发，即视为可能在空中；缺少起飞 ACK 不能恢复“已落地”。这些阈值是工程假设，必须经真机标定；低空悬停和传感偏差仍可能影响判别。

高度边界使用新鲜 `h` 与可信 ToF 的较大值，避免下方桌面使 ToF 读数偏小；缺失有效高度时拒绝普通动作。水平半径仍是已确认请求的积分估计，不能检测风漂或碰撞。越界终止普通任务，恢复降落不受边界门控。


## 默认配置及依据

| 配置 | 当前取值 | 属性 |
| --- | --- | --- |
| 初始请求速度 | 50 cm/s；CLI `--speed` 可设 10–100 | 项目选择，SDK 定义范围，不保证实测速度 |
| 仿真速度控制 | 按请求速度推进 PID 位置参考目标 | 仿真实现，实际机体会有跟踪误差 |
| 指令间隔 | 至少 0.1 秒 | 传输策略，参考 DJITelloPy，不是官方强制时限 |
| 普通动作超时 | 60 秒 | 项目策略；低速长距离命令需要较长时间 |
| 起飞/降落超时 | 各 20 秒 | 项目策略；超时不能伪报成功 |
| 空闲保活 | 每 5 秒 `rc 0 0 0 0` 语义 | 运行层维护，单独记录，不算模型飞行动作；真机后端实发该指令，仿真不发送任何内容并在 trace 中记 `command: null` |
| 空闲中断界限 | 15 秒后终止并收尾 | 对应官方无指令自动降落规则；仿真由 Runtime 发起收尾 |
| 相机图像 | **960×720，4:3** | 普通 Tello SDK 图传配置；接真机时应校验实际解码尺寸 |
| 导航采样 | 目标 30 帧/秒 | Webots 16 ms tick 量化采样时刻；不会伪称传输延迟为零 |
| 水平 FOV | 现有 1.2252 rad，约 70.2° | 延续工程标定假设；不能把官方未注明方向的 82.6°直接当水平 FOV |
| 自动起飞目标 | 仿真 1.0 m（`simulated_takeoff_height_m`），可在 Config 调整 | **仅仿真**；真机后端使用状态包 `h` 与 ToF，不读取此仿真假设 |
| 电量模型 | 663 秒线性模型，20% 收尾 | 延续当前工程模型，不是 SDK 规范或真机续航承诺 |
| 实验边界 | 半径 35 m / 高度 5 m | 仿真监督参数，不作为模型观测，也不是 Tello SDK 限制 |

模型推理及 `hold` 期间维护保活。阻塞的原子移动命令执行期间不插入零速 RC，避免打断动作；真机长动作的固件保活行为仍需单独验证。Webots 不模拟独立固件在主机完全失效后的自主降落，也不模拟 Wi-Fi/H.264 丢包。

`capture` 等待调用后的新解码视频帧并保存完整 PNG，超时则失败；重复读取缓存帧不会产生新帧 ID 或刷新时间戳。相同像素的新解码帧仍有独立 ID。Tello 不提供实际曝光时钟，真机 `captured_at` 是主机解码完成的墙钟时间，`received_at` 是对应单调时钟时间。这不是手机应用的高分辨率静态照片功能。此前把 720p 推断为 1280×720 的修改已撤回，世界文件、提示词和校验配置均恢复 960×720。

后续新增的 `crop_photo` 是主机端图片处理工具，不是 Tello SDK 飞行或相机命令。它只截取已保存照片的原生像素，输出尺寸单独记录；导航图传仍为完整 960×720。模型可以交付裁剪后的竖幅图，原始曝光始终保留。

## 信息隔离与迁移范围

模型继续只接收 RGB、文字历史、图像 ID/时间、电量、公共飞行状态、预算和请求参数。初始速度是请求设置，不是实测速度。GPS、姿态、高度、实际位移和评测真值仍留在内部。

Webots 使用现有 Mavic2Pro 物理节点及 PID。这次对齐的是命令与输入接口，没有宣称已经建立 Tello 质量、惯性、推力、气动和视频链路的物理模型。起飞高度、动力学、视场角和实际视频尺寸应在真机预检中重新测量。

可选依赖通过 `python -m pip install -e '.[dev,tello]'` 安装，固定 DJITelloPy 2.5.0。`tello_io.py` 在该版本的状态包发布及视频解码发布边界记录时间；升级 SDK 必须重跑接收器测试。初始化由后端统一执行一次 `command`、`speed <initial>`、`streamon`，只在传感流就绪后进入任务。

真机使用 `run --backend tello`；现有工作台仍启动 Webots。真机报告没有 Webots 独立轨迹与接触真值，这些评测项保留未知，不能把后端的落地判定当作独立物理评测。

## 验证与复现

```sh
PYTHONPATH=src .venv/bin/python -m pytest -q
# 后续手动开展无模型 Webots 飞行检查时：
PYTHONPATH=src .venv/bin/python -m drone_agent run --scenario facing --script configs/flight-check.json
```

离线测试覆盖真实 SDK 的单次发送、接收时间戳、冻结画面/遥测、迟到 ACK、起飞丢回复、低电量及完整摄影循环，SDK 网络被替换为假传输，不连接飞机。没有启动新的 Webots 飞行或模型摄影评测；历史运行记录保留原始配置，不与本配置混用。新旧对照实验已按用户要求暂停。

依据：
- [Ryze Tello SDK 2.0 User Guide，pp. 2–7](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf)
- [Ryze Tello 产品规格](https://www.ryzerobotics.com/tello/specs)：标为 HD720P30，未据此推断 16:9 宽度。
- [DJITelloPy 指令实现](https://github.com/damiafuentes/DJITelloPy/blob/master/djitellopy/tello.py)：仅用于库级传输约定核对。
