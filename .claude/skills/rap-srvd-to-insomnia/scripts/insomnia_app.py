#!/usr/bin/env python3
"""Stop / start the Insomnia desktop app around a sync_to_insomnia call.

mcp-insomnia writes Insomnia's NeDB files directly; a running app keeps its own copy in memory
and overwrites them, so the app must be closed while syncing.

  insomnia_app.py status
  insomnia_app.py stop  [--timeout 15]   # graceful close, then force kill (taskkill /F, pkill -9)
  insomnia_app.py start [--exe PATH]

Matches the app by exact process name only, so the node process running mcp-insomnia is never hit.
Exit code: 0 on success, 1 when the app is still running after stop or could not be started.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

WIN_IMAGE = "Insomnia.exe"
POSIX_NAMES = {"darwin": "Insomnia", "linux": "insomnia"}


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def running():
    if os.name == "nt":
        out = run(["tasklist", "/FI", "IMAGENAME eq %s" % WIN_IMAGE, "/NH"]).stdout
        return WIN_IMAGE.lower() in out.lower()
    name = POSIX_NAMES.get(sys.platform, "insomnia")
    return run(["pgrep", "-x", name]).returncode == 0


def wait_gone(timeout):
    end = time.time() + timeout
    while time.time() < end:
        if not running():
            return True
        time.sleep(0.5)
    return not running()


def stop(timeout):
    if not running():
        print("Insomnia is not running")
        return 0
    if os.name == "nt":
        run(["taskkill", "/IM", WIN_IMAGE, "/T"])
        if not wait_gone(timeout):
            run(["taskkill", "/IM", WIN_IMAGE, "/T", "/F"])
    elif sys.platform == "darwin":
        run(["osascript", "-e", 'quit app "Insomnia"'])
        if not wait_gone(timeout):
            run(["pkill", "-9", "-x", POSIX_NAMES["darwin"]])
    else:
        run(["pkill", "-x", POSIX_NAMES["linux"]])
        if not wait_gone(timeout):
            run(["pkill", "-9", "-x", POSIX_NAMES["linux"]])
    if wait_gone(5):
        print("Insomnia stopped")
        return 0
    print("error: Insomnia is still running", file=sys.stderr)
    return 1


def windows_exe():
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "insomnia", "Insomnia.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Insomnia", "Insomnia.exe"),
    ]
    candidates += sorted(glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "insomnia", "app-*",
                                                "Insomnia.exe")), reverse=True)
    return next((c for c in candidates if os.path.isfile(c)), None)


def start(exe):
    if running():
        print("Insomnia is already running")
        return 0
    detached = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        exe = exe or windows_exe()
        if not exe:
            print("error: Insomnia.exe not found, pass --exe", file=sys.stderr)
            return 1
        subprocess.Popen([exe], creationflags=0x00000008 | 0x00000200, **detached)  # DETACHED | NEW_GROUP
    elif sys.platform == "darwin":
        subprocess.Popen(["open", exe] if exe else ["open", "-a", "Insomnia"], **detached)
    else:
        if exe:
            cmd = [exe]
        elif shutil.which("insomnia"):
            cmd = ["insomnia"]
        elif shutil.which("flatpak"):
            cmd = ["flatpak", "run", "rest.insomnia.Insomnia"]
        else:
            print("error: insomnia not found on PATH, pass --exe", file=sys.stderr)
            return 1
        subprocess.Popen(cmd, start_new_session=True, **detached)
    print("Insomnia started")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "stop", "start"])
    ap.add_argument("--timeout", type=float, default=15, help="seconds to wait before force kill")
    ap.add_argument("--exe", help="path to the Insomnia executable (start)")
    args = ap.parse_args()
    if args.command == "status":
        print("running" if running() else "not running")
        return 0
    if args.command == "stop":
        return stop(args.timeout)
    return start(args.exe)


if __name__ == "__main__":
    sys.exit(main())
