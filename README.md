# Flying-Agent

**Language-guided agents for the physical world.**

English · [简体中文](README.zh-CN.md)

**Real-world demo available** · **Early research prototype** · **Source code: Coming soon**

Flying-Agent explores AI agents that understand a goal, observe their surroundings, and act through a drone. We are starting with autonomous photography: turning a natural-language request into a photograph captured in the real world.

## Demo: a flying photographer

> “Take a full-body photo of the man by the window.”

[![Flying-Agent demo excerpts: synchronized agent interface and third-person drone footage](assets/demo-preview.gif)](https://github.com/LZR-S/Flying-Agent/releases/tag/demo-v0.1)

**[Get the full 4K demo](https://github.com/LZR-S/Flying-Agent/releases/download/demo-v0.1/flying-agent-demo-4k.mp4)** · [Demo release](https://github.com/LZR-S/Flying-Agent/releases/tag/demo-v0.1)

The video shows Flying-Agent controlling a physical drone on an Innocell rooftop. The agent takes a photography request, takes off, turns toward the subject, adjusts its viewpoint and framing, saves a photograph, and lands. The interface then displays the result and the agent's own assessment of the photography requirements.

The left panel shows the bilingual agent interface, including the camera view and recorded decisions and actions. The right panel shows synchronized third-person footage. The animation above contains selected excerpts; the full video preserves the complete 1 minute 45 second demo, with labeled still frames where the third-person recording is unavailable.

What this first demo brings together:

- **Intent to action.** A photography goal expressed in ordinary language becomes a sequence of physical actions.
- **A viewpoint that can move.** The drone changes its orientation and height to work toward the requested framing.
- **Feedback from the real world.** The agent observes the scene as the task progresses and adjusts its next action.
- **A visible outcome.** A captured photograph and a readable record of the task make the result inspectable.

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
