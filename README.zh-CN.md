# Flying-Agent

[English](README.md) · 简体中文

完整的前沿 AI Agent 系统已经越来越能够在数字环境中完成自动化编程、研究等复杂长程工作。一个更根本的问题是：**当工作发生在普通人的物理生活中，它们还能做到吗？** 物理任务不能靠随时查询完整状态来完成；Agent 必须从视觉等感知中寻找信息，在空间中行动，把多个步骤连续执行到底，并对遗漏、变化、失败和安全后果负责。

区别于目前还远远不够成熟的人形机器人、机械臂等形态，**我们希望赋予 AI Agent 一个可以在真实三维空间中移动、飞行的本体：无人机。** 我们想要探索 Agent 在可移动本体下的能力边界与应用场景极限。

Flying-Agent 研究的不是“AI Agent 能不能让无人机动起来”，而是 **同一个完整的 Agent 系统能否把无人机作为通用的物理行动身体，独立完成有实际结果的长程 agentic 任务**。

当前使用 **DJI Tello** 无人机，依靠 **FPV 第一人称视觉进行场景感知**，在陌生环境中 zero-shot 执行自然语言摄影任务。用户只需说“给窗台边的男生拍一张全身照”，智能体就会观察场景、在线调整视角与构图、拍照并降落。

当前公开版本为 **v0.1**，初步发布了一组摄影 Agent 功能。摄影是一个普遍、实用且易于理解的应用场景，也适合作为开发和评估具身 Agent 的起点。后续将逐步拓展到视频与 Vlog 创作、巡检、管家、陪伴、娱乐等更多应用，长期目标是构建一个通用飞行 Agent。

## 真机飞行演示

天台演示展示了 Tello 真机上的完整摄影任务；图书馆片段则展示：**准备向尚未看清的后方移动时，Agent 会先回头看看，确认后方是否有足够空间。** 观察也可以是一种主动行动。

<table>
<tr><th>天台摄影</th><th>图书馆：先看再移动</th></tr>
<tr>
<td><a href="https://lzr-s.github.io/Flying-Agent/#rooftop"><img src="assets/demo-preview.gif" alt="天台摄影双视角节选" width="560"></a></td>
<td><a href="https://lzr-s.github.io/Flying-Agent/#library"><img src="assets/library-look-behind.gif" alt="图书馆转身观察片段裁剪预览" width="280"></a></td>
</tr>
</table>

[播放天台完整版](https://lzr-s.github.io/Flying-Agent/#rooftop) · [播放图书馆片段](https://lzr-s.github.io/Flying-Agent/#library)

## Webots 摄影演示

[34 秒海岸露台演示](https://lzr-s.github.io/Flying-Agent/#webots)剪辑呈现了一次 Webots 人像摄影任务：Agent 使用构图参考、调整相机机位、比较实时画面与预期构图，最后拍下人像。参考图是合成图，最终照片来自仿真相机。这个演示重点是**通过行动完成摄影判断**：无人机移动后，人物大小、画面边界、头顶留白和背景随之改变，Agent 再依据真实相机画面检查结果。

<a href="https://lzr-s.github.io/Flying-Agent/#webots"><img src="assets/webots-photography-preview.gif" alt="Webots 海岸露台摄影演示的动态节选" width="760"></a>

[观看 Webots 摄影演示](https://lzr-s.github.io/Flying-Agent/#webots)

## 摄影 Agent Harness · v0.1

Harness 将多模态 Agent、统一任务循环、飞行工具和相机反馈连接起来。Agent 可以搜索与重新寻找目标、调整构图、拍摄、复核并继续优化。近期视觉观察和已保存照片为下一步决策提供证据；搜索与构图由同一循环中的决策驱动，而非两套固定流程。

Harness 由三个相互配合的部分组成：

- **视觉空间记忆：** 保留当前相机画面、近期观察和已拍照片供 Agent 判断；不向它提供预建地图或目标坐标。

- **生成式美学设计：** 可选生成构图参考，再与相机画面核对。Agent 通过调整机位构图，按指定比例使用传感器画面中最大的原生裁切区域。

- **安全可靠执行：** 校验工具调用，逐条调度飞行命令，在 Agent 推理期间维持飞控与监督，并记录完成、拒绝和结果不确定的动作。

Webots 仿真与 DJI Tello 真机使用相同的任务接口。Webots 的 Mavic 2 Pro 模型包含模拟云台关节，但 v0.1 Harness 没有向 Agent 开放或控制这些关节；DJI Tello 本身则没有云台。因此，当前两端都按无可控云台的固定相机运行，Agent 通过移动机体调整视角和构图。飞控遥测由控制器和安全监督使用；任务级场景判断以相机图像为依据。下图说明 Harness 的设计，上方视频是不同的演示，不代表同一次运行。

![Flying-Agent 摄影 Harness：视觉空间记忆、生成式美学设计与安全执行](assets/agent-harness-framework-v1.png)

## 环境安装

需要 **Python 3.12 或更高版本**、[Git LFS](https://git-lfs.com/)，以及用于仿真的 [Webots R2025a](https://github.com/cyberbotics/webots/releases/tag/R2025a)。当前启动流程已在 macOS 验证；仅使用 Tello 真机时不需要安装 Webots。

```sh
git lfs install
git clone https://github.com/LZR-S/Flying-Agent.git
cd Flying-Agent
git lfs pull
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

大型 GLB 资产使用 Git LFS。请通过 Git 克隆并执行 `git lfs pull`；仅下载 GitHub 源码压缩包可能无法取得完整资产。后续命令均在仓库根目录、已激活的虚拟环境中执行。

### API 配置

编辑本地 `.env`，填入自己的接口地址和 API key：

| 模型接口 | 配置项 | 使用方式 |
| --- | --- | --- |
| OpenLux | `BASE_URL` / `API_KEY` | 命令行通过 `--env-file .env` 默认使用；工作台也可选择 |
| 阿里云官方 | `AliCloud_url` / `AliCloud_key` | 在工作台选择阿里云接口 |
| 自定义 | `DRONE_PHOTO_VLM_BASE_URL` / `DRONE_PHOTO_VLM_API_KEY` | 命令行从 `.env` 或环境变量读取；工作台选择自定义接口 |

选择所用服务商支持的、具备视觉与工具调用能力的模型。下方命令行示例使用当前默认模型 `gemini-3.6-flash`，可按需修改 `--model`。模型调用会产生相应服务商的 API 费用。凭据、虚拟环境和运行记录均不纳入 Git。

可选的构图参考图工具通过 Images Edits 接口调用 `gpt-image-2`。生图凭据默认取 `BASE_URL` / `API_KEY`，不跟随决策模型接口的选择变化。需要独立生图服务时，成对设置 `DRONE_PHOTO_IMAGE_BASE_URL` / `DRONE_PHOTO_IMAGE_API_KEY`。如果只配置了 `DRONE_PHOTO_VLM_*`，启用参考图还需单独配置生图凭据；缺少生图凭据不影响普通摄影。命令行可用 `--no-reference`，工作台可取消“参考图工具”来关闭生图。参考图是合成构图建议，不能用于导航或作为最终照片交付。

## 使用指南

### 工作台

```sh
python -m drone_agent dashboard --port 8766 --env-file .env --open
```

工作台地址为 <http://127.0.0.1:8766>；不需要自动打开浏览器时可省略 `--open`。选择场景、模型接口、模型并填写任务后启动，可查看实时画面、工具调用、候选照片和历史报告。界面首次打开默认显示英文，顶栏可切换中文/英文，语言选择会保存在浏览器中。

工作台用于启动 **Webots 仿真**和回放已有运行；Tello 真机通过下方命令行启动。控制操作和报告下载详见[工作台指南](docs/workbench.md)。更新代码后需重启已有工作台服务。

### Webots 命令行

```sh
python -m drone_agent run \
  --scenario hidden \
  --model gemini-3.6-flash \
  --brief '找到人物，拍一张全身照' \
  --env-file .env
```

默认后端为 `webots`，场景包括 `facing`、`open`、`hidden` 和 `terrace`。默认仿真器路径为 `/Applications/Webots.app/Contents/MacOS/webots`，可用 `--webots /path/to/webots` 指定其他安装位置。世界文件使用固定 R2025a PROTO 来源，首次加载可能需要网络。

### DJI Tello 命令行

在同一虚拟环境中安装真机可选依赖：

```sh
python -m pip install -e '.[dev,tello]'
```

开启 Tello 并将电脑连接到其 Wi-Fi，同时保留模型 API 所需的互联网连接，例如通过另一块网络接口。以下命令会控制真实飞机并可能起飞，请在空旷飞行区域、有人值守时运行。

```sh
python -m drone_agent run \
  --backend tello \
  --model gemini-3.6-flash \
  --brief '找到人物，拍一张全身照' \
  --env-file .env
```

默认飞机地址为 `192.168.10.1`，可用 `--tello-ip` 覆盖。飞行动作语义与遥测限制详见 [Tello 动作契约与后端说明](docs/tello-profile.md)。

### 画幅与运行结果

两个后端均支持 `--default-aspect-ratio`（默认 `16:9`）、`--guides none|thirds|golden`（默认 `thirds`）和 `--no-reference`。默认 `--framing-policy max_native` 按指定比例保留最大的原生裁切区域；仅在任务允许更小裁切时，于启动前选择 `--framing-policy flexible`，模型不能自行切换该策略。

运行输出保存在 `runs/`，包含照片、模型请求与回复、事件、评测结果、JSON/CSV 导出及 HTML 报告。可用 `--output /path/to/run` 指定新的运行目录。重新生成已有运行的评测与报告时，将 `RUN_ID` 替换为对应的目录名：

```sh
python -m drone_agent evaluate runs/RUN_ID
```

完整命令行选项可通过 `python -m drone_agent run --help` 查看。

## 离线测试

```sh
python -m pytest
```

离线测试不启动 Webots，也不调用模型 API。安装 `.[dev,tello]` 后，还会通过模拟网络传输测试真实 DJITelloPy 接收器代码，不连接飞机。未安装该可选依赖时，仅跳过 SDK 接收器测试，其余 Tello 后端故障测试仍运行。

仓库独立提供 v1 运行时，不分发旧版冻结快照 `baseline/v0/`；缺少该快照时，仅跳过依赖它的测试。历史 `benchmark` 对照入口需要另行准备该快照。

## 技术文档

- [模型工具协议与上下文](docs/native-tools.md)
- [摄影工作台](docs/workbench.md)
- [Tello 动作契约与仿真边界](docs/tello-profile.md)
- [场景资产清单](configs/assets.json)

## 后续计划

我们计划持续完善和更新 Harness，公开更多完整演示，以及供外部检查任务执行过程的文档。Harness 也会持续围绕感知、构图和可靠飞行改进。

更长期的研究计划包括开源针对这些任务专门训练的模型及其数据管线，并将 Harness 完善为 **System 2 & System 1 架构**——例如使用 Jev 作为 System 1，承担避障、导航等快速局部能力，与负责长程任务的多模态 Agent（**System 2**）协同工作。我们将研究双系统在飞行中的配合方式。这些是计划中的发布与研究方向，不代表上方演示已经具备相应能力。

摄影之外，我们还会探索视频与 Vlog 创作、巡检、管家、陪伴、娱乐、多机器人协作等更多应用，目标是通用 **Flying Agent**，乃至通用 **Phygital Agent**。欢迎交流与合作。
