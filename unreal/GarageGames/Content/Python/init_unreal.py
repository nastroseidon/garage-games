"""Runs when the Garage Games project opens in the Unreal editor (Unreal runs
every init_unreal.py in Content/Python at startup).

Starts following the Garage Games server, so shots play in the level
viewport. The server can be started before or after the editor.
"""

import unreal

try:
    import garage_bridge
    garage_bridge.start()
except Exception as exc:  # a broken bridge must not stop the editor from opening
    unreal.log_error("[Garage Games] could not start the shot bridge: %r" % exc)
