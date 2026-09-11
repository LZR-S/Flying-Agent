# Flying-Agent

**Zero-shot drone photography. First-person vision. Physical-world action.**

English · [简体中文](README.zh-CN.md)

**Real-world demo available** · **Early research prototype** · **Source code: Coming soon**

Inspired by recent GPT6-Astra robot-arm demos, we tried a different embodiment: **let an AI agent control a drone to take a photograph, zero-shot.**

Flying-Agent turns a natural-language photography request into physical action. It sees the scene through a first-person RGB camera, adjusts its viewpoint and composition as it goes, and checks the space it is about to move into.

One behavior that stood out: **before moving backward into an unseen area, it turns to look behind and checks whether the way is clear.**

## Demo: a flying photographer

> “Take a full-body photo of the man by the window.”

[![Flying-Agent demo excerpts: synchronized agent interface and third-person drone footage](assets/demo-preview.gif)](https://github.com/LZR-S/Flying-Agent/releases/tag/demo-v0.1)

**[Get the full 4K demo](https://github.com/LZR-S/Flying-Agent/releases/download/demo-v0.1/flying-agent-demo-4k.mp4)** · [Demo release](https://github.com/LZR-S/Flying-Agent/releases/tag/demo-v0.1)

The video shows Flying-Agent controlling a physical drone on an Innocell rooftop. The agent takes a photography request, takes off, turns toward the subject, adjusts its viewpoint and framing, saves a photograph, and lands. The interface then displays the result and the agent's own assessment of the photography requirements.

The left panel shows the bilingual agent interface, including the camera view and recorded decisions and actions. The right panel shows synchronized third-person footage. The animation above contains selected excerpts; the full video preserves the complete 1 minute 45 second demo, with labeled still frames where the third-person recording is unavailable.

## What we are exploring

- **Zero-shot task execution.** Give the agent a photography goal in ordinary language. Here, zero-shot means using pretrained models without task-specific fine-tuning for this demo.
- **First-person visual perception.** The drone's RGB camera provides its view of the scene.
- **Online composition.** The agent adjusts its orientation and height in response to what it sees and the framing requested.
- **Scene adaptation.** Decisions respond to the current scene and photography goal. We will share broader generalization results as more demos are released.
- **Obstacle-aware motion.** The system checks the intended path and can reject a move when clearance is unknown or insufficient. Looking behind before a retreat is one concrete example.

These are capabilities of the agent system as a whole. The current prototype's visual obstacle checks cover a bounded setting; broader robustness remains part of our research.

## Why a flying agent?

For a physical agent, where it looks is part of what it does. Moving a camera can reveal a subject, change a composition, or provide the evidence needed for the next decision.

Photography gives us a concrete place to explore this idea. The agent has to connect human intent with a changing visual scene, physical motion, and an outcome that people can inspect. We see this as an early step toward agents that can carry out useful tasks beyond a screen.

## Where we want to go

These are directions we want to explore as the project develops:

| Direction | What we would like to make possible |
| --- | --- |
| **Creative assistance** | Help people find better viewpoints, compose portraits, and capture short visual stories. |
| **Active observation** | Move to gather a missing view, look at a scene from multiple angles, and answer questions with visual evidence. |
| **Spatial inspection** | Help document a space or an object and revisit viewpoints to understand what has changed. |
| **Physical collaboration** | Work with people, ground robots, and other agents on tasks that benefit from complementary perspectives. |

Across these directions, we want physical actions to remain understandable, outcomes to be inspectable, and people to stay in control. The broader capabilities above are research goals; the current public demonstration focuses on photography.

## Open-source roadmap

**Source code: Coming soon.**

This initial release shares the project overview and demo. The core implementation and detailed technical documentation will follow in future releases.

- [x] Publish the first real-world photography demo.
- [x] Share the project direction.
- [ ] Open-source the implementation, setup instructions, and reproducible examples.
- [ ] Release more demos and expand the set of supported tasks.

We will continue open-sourcing our work as Flying-Agent develops, sharing code, experiments, and demos that help it do more useful and interesting things in the physical world.

## Follow along

Star or watch this repository for upcoming releases. Ideas for useful tasks, creative demos, and physical-agent research are welcome in [Issues](https://github.com/LZR-S/Flying-Agent/issues).
