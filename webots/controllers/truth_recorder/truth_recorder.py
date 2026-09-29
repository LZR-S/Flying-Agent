"""Independent truth recorder. Only a terminal abort signal crosses to runtime."""
import json
import math
import os
import time
from pathlib import Path
from controller import Supervisor

robot=Supervisor();dt=int(robot.getBasicTimeStep())
drone=robot.getFromDef('DRONE');subject=robot.getFromDef('PERSON_B')
directory=Path(os.environ['DRONE_AGENT_RUN'])/'evaluation';directory.mkdir(parents=True,exist_ok=True)
config=json.loads(Path(os.environ['DRONE_AGENT_CONFIG']).read_text())
origin=list(drone.getPosition());wall0=time.monotonic();sim0=robot.getTime()
with (directory/'truth.jsonl').open('w',buffering=1) as stream:
 while robot.step(dt)!=-1:
  # Apply the same pacing even when an older controller stops stepping during API calls.
  lead=robot.getTime()-sim0-(time.monotonic()-wall0)
  if lead>0:time.sleep(lead)
  position=list(drone.getPosition());contacts=drone.getContactPoints(True)
  rotation=subject.getField('rotation').getSFRotation()
  row={'wall_time':time.time(),'simulation_time':robot.getTime(),'position':position,
       'orientation':list(drone.getOrientation()),'subject_position':list(subject.getPosition()),
       'subject_facing_rad':rotation[3]*rotation[2]-math.pi/2,
       'contact_heights':[p.point[2] for p in contacts],
       'contacts':[{'point':list(p.point),'node_id':p.node_id} for p in contacts]}
  stream.write(json.dumps(row)+'\n')
  if (math.hypot(position[0]-origin[0],position[1]-origin[1])>config.get('radius_m',35.)+.15 or
      position[2]>config.get('ceiling_m',5.)+.15):
   (directory/'abort.signal').touch()
