"""Port management utilities for ensuring clean server startup."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import logging


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is currently open and accepting connections or bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        try:
            res = s.connect_ex((host, port))
            if res == 0:
                return True
        except Exception:
            pass

    # Also test binding
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return False
    except OSError:
        return True


def get_pids_on_port(port: int) -> set[int]:
    """Retrieve all active Process IDs (PIDs) listening on the specified TCP port."""
    pids: set[int] = set()
    current_pid = os.getpid()

    if platform.system() == "Windows":
        try:
            output = subprocess.check_output(
                "netstat -ano -p tcp",
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 4:
                    local_addr = parts[1]
                    if local_addr.endswith(f":{port}") or local_addr.endswith(f"]:{port}"):
                        pid_str = parts[-1]
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if pid != 0 and pid != current_pid:
                                pids.add(pid)
        except Exception:
            pass
    else:
        # Linux / macOS fallback using lsof or fuser
        try:
            output = subprocess.check_output(
                ["lsof", "-t", f"-i:{port}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in output.splitlines():
                pid_str = line.strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    if pid != current_pid:
                        pids.add(pid)
        except Exception:
            pass

    return pids


def kill_process_on_port(port: int, max_wait_s: float = 2.0) -> list[int]:
    """Terminate all processes listening on or holding the specified port.
    
    Returns the list of terminated PIDs.
    """
    pids = get_pids_on_port(port)
    if not pids:
        return []

    killed_pids: list[int] = []
    for pid in pids:
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    f"taskkill /F /PID {pid}",
                    shell=True,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, 9)
            killed_pids.append(pid)
        except Exception:
            pass

    # Wait up to max_wait_s for the OS socket to release
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        if not is_port_in_use(port):
            break
        time.sleep(0.1)

    return killed_pids


def ensure_port_available(
    port: int,
    host: str = "127.0.0.1",
    logger: logging.Logger | None = None,
) -> list[int]:
    """Ensure the specified port is completely free. If taken, kill the occupant(s)."""
    if not is_port_in_use(port, host):
        return []

    killed = kill_process_on_port(port)
    if killed and logger:
        logger.info(
            "Port %d was occupied. Terminated process(es) with PID(s): %s",
            port,
            killed,
        )
    return killed
