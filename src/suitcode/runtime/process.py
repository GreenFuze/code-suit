from __future__ import annotations

import os
import signal
import subprocess
import time


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate_process(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        deadline = time.time() + 5.0
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            )
        except subprocess.TimeoutExpired:
            return not is_process_running(pid)
        while time.time() < deadline:
            if not is_process_running(pid):
                return True
            time.sleep(0.1)
        return not is_process_running(pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True
    deadline = time.time() + 5
    while time.time() < deadline:
        if not is_process_running(pid):
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return True
    deadline = time.time() + 1
    while time.time() < deadline:
        if not is_process_running(pid):
            return True
        time.sleep(0.1)
    return not is_process_running(pid)
