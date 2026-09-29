"""Real-aircraft entry point: no Webots, no robot, no simulation clock.

`controller.py` cannot serve this path. Its first statement is `from controller
import Robot`, which only exists inside a Webots controller process, and
`WebotsBackend` additionally depends on a supervisor writing `abort.signal` for
the geofence. So the hardware run is a second entry point rather than a branch
inside the first, which is what `tasks/todo.md` anticipated.

Everything downstream of the backend is shared unchanged: the same `Runtime`
state machine, the same `AgentLoop`, the same evidence archive. Only the
aircraft adapter and the way the mission is launched differ.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .agent import AgentLoop
from .artifacts import Artifacts
from .protocol import Config
from .provider import CloudPolicy, load_credentials
from .runtime import Runtime
from .tello_backend import TelloBackend


def connect(config: Config):
    """Construct the optional SDK; TelloBackend owns its single connection handshake.

    Raised as a plain `RuntimeError` rather than `SystemExit` so the caller can
    report a failed link the same way it reports any other startup fault.
    """
    try:
        from .tello_io import ManagedTello
    except ImportError as error:
        raise RuntimeError('djitellopy is required for --backend tello') from error
    return ManagedTello(host=config.tello_ip)


def run(config: Config, directory: Path, *, preview=True, aircraft=None):
    """Fly one mission on hardware. Returns the summary dict that was written."""
    directory = Path(directory).resolve()
    artifacts = Artifacts(directory, config)
    writer = None
    if preview:
        from .preview import PreviewWriter

        writer = PreviewWriter(directory)
    backend = None
    try:
        backend = TelloBackend(aircraft or connect(config), config)
        backend.connect()
        runtime = Runtime(backend, config, artifacts, preview=writer)
        policy = CloudPolicy(config, artifacts)
        from .reference import ReferenceGenerator

        generator = ReferenceGenerator(config, artifacts) if config.max_references else None
        AgentLoop(runtime, policy, artifacts, config, reference_generator=generator).run()
    except Exception as error:
        artifacts.event('controller_error', {'type': type(error).__name__})
        if not (directory / 'summary.json').exists():
            artifacts.finish({'status': 'aborted', 'reason': 'controller_initialization_error',
                              'selected': None, 'selected_id': None, 'landing': None,
                              'landed': False})
    finally:
        if writer is not None:
            writer.close()
        if backend is not None:
            backend.close()
    return json.loads((directory / 'summary.json').read_text())


def main():
    """Environment-driven, so `cli.py` launches this the way it launches Webots."""
    config = Config.model_validate_json(Path(os.environ['DRONE_AGENT_CONFIG']).read_text())
    load_credentials(Path(os.environ.get('DRONE_AGENT_ENV_FILE', '.env')))
    directory = Path(os.environ.get('DRONE_AGENT_RUN') or
                     f'runs/tello-{datetime.now():%Y%m%d-%H%M%S}')
    summary = run(config, directory)
    print(json.dumps(summary, ensure_ascii=False))
    return 0
