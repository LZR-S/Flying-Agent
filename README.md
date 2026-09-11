# Flying-Agent

English · [简体中文](README.zh-CN.md)

**We want to give AI agents a body that can fly.** Flying-Agent explores an embodiment distinct from screen-based digital agents, humanoid robots, and robotic arms. By bringing movement, observation, and action together, we aim to explore the limits of what agents with mobile bodies can do and where they can be useful. Drone photography is our starting point.

We use a **DJI Tello**, relying solely on **first-person vision (FPV) for scene perception** in unfamiliar environments and carrying out natural-language photography tasks zero-shot. Given “Take a full-body photo of the man by the window,” the agent observes the scene, adjusts its viewpoint and composition online, captures a photograph, and lands.

The rooftop demo shows the complete task. A library clip highlights behavior in another setting: **before moving backward into an area it has not yet seen clearly, the agent turns to look behind and checks whether there is enough room.** Observation can itself be a deliberate action.

<table>
<tr><th>Rooftop photography</th><th>Library: look before moving</th></tr>
<tr>
<td><a href="https://github.com/LZR-S/Flying-Agent/releases/download/demo-v0.1/flying-agent-demo-4k.mp4"><img src="assets/demo-preview.gif" alt="Synchronized rooftop photography demo excerpts" width="560"></a></td>
<td><a href="https://github.com/LZR-S/Flying-Agent/releases/download/demo-v0.2/flying-agent-library-look-behind.mp4"><img src="assets/library-look-behind.gif" alt="Cropped library preview showing the drone turn to inspect its surroundings" width="280"></a></td>
</tr>
</table>

[Full rooftop demo · 4K](https://github.com/LZR-S/Flying-Agent/releases/download/demo-v0.1/flying-agent-demo-4k.mp4) · [Full library clip](https://github.com/LZR-S/Flying-Agent/releases/download/demo-v0.2/flying-agent-library-look-behind.mp4)

Next, we want to explore active observation, spatial inspection, creative recording, and collaboration among agents—helping a flying embodiment do useful and interesting things across more environments.

**Code: Coming soon.** We are sharing the project overview and demos now, and will continue open-sourcing code, documentation, and examples for more tasks.
