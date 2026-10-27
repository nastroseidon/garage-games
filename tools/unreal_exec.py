"""Run Python in the open Unreal editor from a terminal.

Uses Unreal's own remote execution (it ships with the Python Editor Script
Plugin). The project turns it on in Config/DefaultEngine.ini, and it only
listens on this PC.

    python tools/unreal_exec.py path/to/script.py
    python tools/unreal_exec.py -c "import garage_bridge; garage_bridge.status()"

Finds Unreal 5.8 from the Epic Games Launcher; pass --engine E:\\UE_5.8 for
another install.
"""

import argparse
import json
import os
import sys
import time

LAUNCHER_LIST = r"C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat"


def find_engine(version="5.8"):
    try:
        with open(LAUNCHER_LIST, encoding="utf-8") as f:
            for app in json.load(f)["InstallationList"]:
                if app["AppName"] == "UE_" + version:
                    return app["InstallLocation"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("script", nargs="?", help="a .py file to run in the editor")
    parser.add_argument("-c", dest="code", help="Python code to run instead of a file")
    parser.add_argument("--engine", default=os.environ.get("UE_ENGINE_DIR") or find_engine(),
                        help="Unreal Engine install folder (default: UE 5.8 from the Epic Games Launcher)")
    parser.add_argument("--project", default="GarageGames", help="only talk to an editor with this project open")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for the editor")
    args = parser.parse_args()
    if not (args.script or args.code):
        parser.error("give a script file or -c CODE")
    if not args.engine:
        raise SystemExit("Can't find Unreal Engine 5.8; pass --engine <install folder>.")

    sys.path.insert(0, os.path.join(args.engine, "Engine", "Plugins", "Experimental", "PythonScriptPlugin",
                                    "Content", "Python"))
    import remote_execution as rx  # ships with Unreal

    command = args.code if args.code else os.path.abspath(args.script)
    remote = rx.RemoteExecution()
    remote.start()
    try:
        node, end = None, time.monotonic() + args.timeout
        while node is None and time.monotonic() < end:
            for n in remote.remote_nodes:
                if n.get("project_name") == args.project:
                    node = n
            time.sleep(0.1)
        if node is None:
            raise SystemExit("No Unreal editor with the %s project answered. Is it open, with remote "
                             "execution on (Config/DefaultEngine.ini)?" % args.project)
        remote.open_command_connection(node["node_id"])
        result = remote.run_command(command, unattended=True, exec_mode=rx.MODE_EXEC_FILE)
    finally:
        remote.stop()
    for line in result.get("output", []):
        print(("" if line["type"] == "Info" else line["type"] + ": ") + line["output"].rstrip())
    if not result.get("success"):
        print(result.get("result", ""), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
