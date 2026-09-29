# Flying-Agent

English · [简体中文](README.zh-CN.md)

Complete frontier AI agent systems are increasingly able to carry out complex, long-horizon work in digital environments, including automated programming and research. A more fundamental question remains: **can they do the same when work takes place in ordinary people's physical lives?** Physical tasks cannot be completed by querying a complete state at every moment. An agent must find information through vision and other forms of perception, move through space, execute multiple steps continuously to completion, and take responsibility for omissions, change, failure, and safety consequences.

Unlike the still far-from-mature forms of humanoid robots and robotic arms, **we want to give AI agents a body that can move and fly in real 3D space: a drone.** We aim to explore the limits and application frontiers of agents with mobile embodiments.

Flying-Agent does not ask merely whether an AI agent can make a drone move. It asks whether **one complete agent system can use a drone as a general-purpose physical body to independently accomplish long-horizon agentic tasks with real-world outcomes**.

We use a **DJI Tello**, relying on **first-person vision (FPV) for scene perception** in unfamiliar environments and carrying out natural-language photography tasks zero-shot. Given “Take a full-body photo of the man by the window,” the agent observes the scene, adjusts its viewpoint and composition online, captures a photograph, and lands.

The current public release is **v0.1**, which provides an initial set of photography-agent capabilities. Photography is a common, broadly useful application and a clear starting point for developing and evaluating an embodied agent. We plan to expand step by step into video and vlog creation, inspection, household assistance, companionship, entertainment, and other applications. The long-term goal is a general-purpose flying agent.

## Real-world flight demos

The rooftop demo shows a complete photography task on a real Tello. A library clip highlights behavior in another setting: **before moving backward into an area it has not yet seen clearly, the agent turns to look behind and checks whether there is enough room.** Observation can itself be a deliberate action.

<table>
<tr><th>Rooftop photography</th><th>Library: look before moving</th></tr>
<tr>
<td><a href="https://lzr-s.github.io/Flying-Agent/#rooftop"><img src="assets/demo-preview.gif" alt="Synchronized rooftop photography demo excerpts" width="560"></a></td>
<td><a href="https://lzr-s.github.io/Flying-Agent/#library"><img src="assets/library-look-behind.gif" alt="Cropped library preview showing the drone turn to inspect its surroundings" width="280"></a></td>
</tr>
</table>

[Watch rooftop demo · 4K](https://lzr-s.github.io/Flying-Agent/#rooftop) · [Watch library clip](https://lzr-s.github.io/Flying-Agent/#library)

## Webots photography demo

The [34-second coastal-terrace demo](https://lzr-s.github.io/Flying-Agent/#webots) is a condensed, edited view of a Webots portrait task. It shows the agent using a composition reference, adjusting its camera viewpoint, comparing the live frame with the intended composition, and capturing a final portrait. The reference image is synthetic; the final photograph comes from the simulated camera. This demo focuses on **photographic judgment through action**: subject scale, framing, headroom, and background are changed by moving the drone, then checked against the real camera view.

<a href="https://lzr-s.github.io/Flying-Agent/#webots"><img src="assets/webots-photography-preview.gif" alt="Animated excerpts from the Webots coastal-terrace photography demo" width="760"></a>

[Watch the Webots photography demo](https://lzr-s.github.io/Flying-Agent/#webots)

## Photography agent harness · v0.1

Our harness connects a multimodal agent to a shared task loop, flight tools, and camera feedback. The agent can search, re-find a subject, adjust composition, capture, review, and iterate. Recent visual observations and saved photos provide evidence for the next decision; search and composition are decisions within the same loop rather than separate fixed workflows.

The harness has three cooperating parts:

- **Visual-spatial memory:** Keeps the current camera view, recent observations, and saved photos available for visual decisions without handing the agent a prebuilt map or target coordinates.

- **Generative aesthetic design:** Can produce an optional composition reference, then checks it against camera images. The agent adjusts viewpoint and uses the largest native crop of the requested aspect ratio when framing the shot.

- **Safe and reliable execution:** Validates tool calls, runs one flight command at a time, supervises control while the agent thinks, and records completed, rejected, or uncertain actions.

The same task interface supports Webots simulation and DJI Tello hardware. The Webots Mavic 2 Pro model contains simulated gimbal joints, but the v0.1 harness does not expose or control them; the DJI Tello itself has no gimbal. Both backends therefore operate as fixed-camera systems without agent-controllable gimbal movement, and the agent changes its viewpoint and composition by moving the aircraft. Flight telemetry remains available to the controller and safety supervision; task-level scene decisions are grounded in camera images. The diagram describes the harness design; the videos above are separate demonstrations and should not be treated as identical runs.

![Flying-Agent photography harness: visual-spatial memory, generative aesthetic design, and safe execution](assets/agent-harness-framework-v1.png)

## Installation

Requirements: **Python 3.12 or later**, [Git LFS](https://git-lfs.com/), and [Webots R2025a](https://github.com/cyberbotics/webots/releases/tag/R2025a) for simulation. The current launch workflow has been validated on macOS. Tello-only use does not require Webots.

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

Large GLB assets are stored in Git LFS. Use a Git clone followed by `git lfs pull`; downloading the GitHub source ZIP may leave these assets unavailable. Run the commands below from the repository root with the virtual environment activated.

### API configuration

Edit the local `.env` file with your endpoint and API key:

| Provider | Configuration | Where to select it |
| --- | --- | --- |
| OpenLux | `BASE_URL` / `API_KEY` | Default for the CLI with `--env-file .env`; also available in the workbench |
| AliCloud | `AliCloud_url` / `AliCloud_key` | Select AliCloud in the workbench |
| Custom | `DRONE_PHOTO_VLM_BASE_URL` / `DRONE_PHOTO_VLM_API_KEY` | Set in `.env` or the environment for the CLI; select Custom in the workbench |

Choose a vision model with tool-calling support that is available through your provider. The CLI example below uses the current default, `gemini-3.6-flash`; change `--model` as needed. Model calls use your configured provider and incur its API charges. Credentials, virtual environments, and run records are excluded from Git.

The optional composition-reference tool uses `gpt-image-2` through the Images Edits API. Its credentials default to `BASE_URL` / `API_KEY`, independently of the selected decision-model provider. To use a separate image provider, set both `DRONE_PHOTO_IMAGE_BASE_URL` and `DRONE_PHOTO_IMAGE_API_KEY`. If you only configure `DRONE_PHOTO_VLM_*`, configure image credentials separately to enable this tool. Missing image credentials do not prevent ordinary photography. Disable references with `--no-reference` or the workbench's reference-tool toggle. References are synthetic composition suggestions, not navigation evidence or deliverable photos.

## Usage

### Workbench

```sh
python -m drone_agent dashboard --port 8766 --env-file .env --open
```

The workbench opens at <http://127.0.0.1:8766>; omit `--open` to skip opening a browser automatically. Select a scene, provider, model, and task, then start the run. The interface shows the live camera, tool calls, candidate photos, and historical reports. It defaults to English, with a persistent Chinese/English toggle in the top bar.

The workbench launches **Webots simulation** and replays existing runs. Use the CLI below to launch Tello hardware. See the [workbench guide](docs/workbench.md) for controls and report downloads. Restart an existing workbench service after updating the code.

### Webots command line

```sh
python -m drone_agent run \
  --scenario hidden \
  --model gemini-3.6-flash \
  --brief 'Find the person and take a full-body photo' \
  --env-file .env
```

The default backend is `webots`. Available scenes are `facing`, `open`, `hidden`, and `terrace`. The default simulator executable is `/Applications/Webots.app/Contents/MacOS/webots`; use `--webots /path/to/webots` for another installation. World files reference fixed R2025a PROTO sources, so the first load may require network access.

### DJI Tello command line

Install the optional hardware dependency in the same virtual environment:

```sh
python -m pip install -e '.[dev,tello]'
```

Power on the Tello and connect the computer to its Wi-Fi. Keep internet access available for the model API, for example through a separate network interface. The following command controls the real aircraft and can take off; run it in a clear flight area with an operator present.

```sh
python -m drone_agent run \
  --backend tello \
  --model gemini-3.6-flash \
  --brief 'Find the person and take a full-body photo' \
  --env-file .env
```

The default aircraft address is `192.168.10.1`; override it with `--tello-ip` if needed. See the [Tello action contract and backend notes](docs/tello-profile.md) for flight-command semantics and telemetry limitations.

### Framing and output

Both backends accept `--default-aspect-ratio` (default `16:9`), `--guides none|thirds|golden` (default `thirds`), and `--no-reference`. The default `--framing-policy max_native` keeps the largest native crop for the requested aspect ratio. Use `--framing-policy flexible` before launch only when the task permits smaller crops; the agent cannot switch this policy itself.

Runs are saved under `runs/` with photos, model requests and responses, events, evaluation results, JSON/CSV exports, and an HTML report. Use `--output /path/to/run` to choose a new run directory. To regenerate an existing run's evaluation and reports, replace `RUN_ID` with its directory name:

```sh
python -m drone_agent evaluate runs/RUN_ID
```

For all CLI options, run `python -m drone_agent run --help`.

## Offline tests

```sh
python -m pytest
```

Offline tests do not launch Webots or call model APIs. With `.[dev,tello]` installed, they also test the real DJITelloPy receiver code using mocked network transport, without connecting to an aircraft. Without that optional dependency, only the SDK receiver tests are skipped; the remaining Tello fault tests still run.

The repository includes the standalone v1 runtime. The frozen legacy snapshot at `baseline/v0/` is not distributed; tests requiring that snapshot are skipped when it is absent. The historical `benchmark` command requires the snapshot separately.

## Technical documentation

- [Model tool protocol and context](docs/native-tools.md)
- [Photography workbench](docs/workbench.md)
- [Tello action contract and simulation boundaries](docs/tello-profile.md)
- [Scene asset manifest](configs/assets.json)

## Roadmap

We plan to keep improving and updating the harness, publish more complete demonstrations, and provide documentation that lets others inspect how tasks were executed. Development will continue across perception, composition, and reliable flight.

Our longer-term research plan includes open-sourcing models trained specifically for these tasks and their data pipelines, and developing the harness into a **System 2 & System 1 architecture**—for example, using Jev as System 1 for fast local capabilities such as obstacle avoidance and navigation, alongside the deliberative multimodal agent as **System 2**. We will study how the two systems can cooperate during flight. These are planned releases and research directions, not capabilities claimed for the demos above.

Beyond photography, we will explore video and vlog creation, inspection, household assistance, companionship, entertainment, multi-robot collaboration, and more. Our goal is a general-purpose **Flying Agent**, and eventually a general-purpose **Phygital Agent**. We welcome discussion and collaboration.
