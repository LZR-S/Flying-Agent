# Flying-Agent

English · [简体中文](README.zh-CN.md)

Complete frontier AI agent systems are increasingly able to carry out complex, long-horizon work in digital environments—programming, research, and tool use among them. A more fundamental question remains: **can they do the same when work takes place in ordinary people's physical lives?** Physical tasks cannot be completed by querying a complete state at every moment. An agent must find information from partial visual observations, move through space, execute multiple steps continuously to completion, and take responsibility for omissions, change, failure, and safety consequences.

Unlike the still far-from-mature forms of humanoid robots and robotic arms, **we want to give AI agents a body that can move and fly in real 3D space: a drone.** We aim to explore the limits and application frontiers of agents with mobile embodiments. Drone photography is only the starting point.

Flying-Agent does not ask merely whether an AI agent can make a drone move. It asks whether **one complete agent system can use a drone as a general-purpose physical body to independently accomplish long-horizon agentic tasks with real-world outcomes**.

We use a **DJI Tello**, relying solely on **first-person vision (FPV) for scene perception** in unfamiliar environments and carrying out natural-language photography tasks zero-shot. Given “Take a full-body photo of the man by the window,” the agent observes the scene, adjusts its viewpoint and composition online, captures a photograph, and lands.

The rooftop demo shows the complete task. A library clip highlights behavior in another setting: **before moving backward into an area it has not yet seen clearly, the agent turns to look behind and checks whether there is enough room.** Observation can itself be a deliberate action.

<table>
<tr><th>Rooftop photography</th><th>Library: look before moving</th></tr>
<tr>
<td><a href="https://lzr-s.github.io/Flying-Agent/#rooftop"><img src="assets/demo-preview.gif" alt="Synchronized rooftop photography demo excerpts" width="560"></a></td>
<td><a href="https://lzr-s.github.io/Flying-Agent/#library"><img src="assets/library-look-behind.gif" alt="Cropped library preview showing the drone turn to inspect its surroundings" width="280"></a></td>
</tr>
</table>

[Watch rooftop demo · 4K](https://lzr-s.github.io/Flying-Agent/#rooftop) · [Watch library clip](https://lzr-s.github.io/Flying-Agent/#library)

Minimal electronic soundtrack edition. Click either preview to watch with playback controls and fullscreen.

Next, we will explore inspection, companionship, entertainment, and multi-drone collaboration—helping a flying embodiment do useful and interesting things across more environments.

**Code: Coming soon.** We are sharing the project overview and demos now, and will continue open-sourcing code, documentation, and examples for more tasks.
