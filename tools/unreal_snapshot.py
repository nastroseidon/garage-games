"""Save a screenshot of the Unreal range from a chosen camera position.

Runs inside the editor, sent with tools/unreal_exec.py. Handy for checking
how the range looks without playing a shot:

    python tools/unreal_exec.py -c "import sys; sys.argv=['', 'night_overview', '-26,0,30', '95,0,-8', '38']; exec(open(r'G:/Projects/Garage-Games/tools/unreal_snapshot.py').read())"

(use the full path to this file: the editor runs from its own folder).

Arguments: name, camera position "x,y,z" (yards), look-at point "x,y,z"
(yards), vertical field of view (degrees). Saved to the project's
Saved/Screenshots/WindowsEditor/<name>.png.
"""

import sys

import unreal

import garage_bridge
import garage_stream as gs

name = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
pos = [float(v) for v in (sys.argv[2] if len(sys.argv) > 2 else "-26,0,30").split(",")]
look = [float(v) for v in (sys.argv[3] if len(sys.argv) > 3 else "95,0,-8").split(",")]
fov = float(sys.argv[4]) if len(sys.argv) > 4 else 38.0

cam = garage_bridge.find_actor(garage_bridge.CAMERA)
p, l = gs.to_unreal(pos), gs.to_unreal(look)
pitch, yaw, roll = gs.look_rotation(p, l)
cam.set_actor_location_and_rotation(unreal.Vector(*p), unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw), False, False)
cam.camera_component.set_field_of_view(gs.horizontal_fov(fov))
unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, name + ".png", camera=cam)
print("saved", name)
