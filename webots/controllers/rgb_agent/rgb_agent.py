import os
import runpy
import sys
from pathlib import Path
baseline=os.getenv("DRONE_AGENT_BASELINE")
if baseline:
    runpy.run_path(str(Path(baseline)/"runner.py"),run_name="__main__")
else:
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"src"))
    from drone_agent.controller import main
    main()
