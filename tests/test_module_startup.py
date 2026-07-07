import os
import signal
import socket
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest


TEST_CFG_PATH = Path("./tests/resources/test_cfg.toml")


def test_run_control_room():
    test_cfg_path = TEST_CFG_PATH

    cfg = tomllib.load(open(test_cfg_path, "rb"))
    print(cfg)

    print("Sys executable:", sys.executable)
    # Start the control room in a subprocess, capturing stdout and stderr so we can debug if it fails
    proc = subprocess.Popen(
        [sys.executable, "-m", "control_room.main", "--setup-cfg-path", test_cfg_path],
        # stdout=subprocess.PIPE,   # -- just have the STDOUT shown
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    print("Started control room subprocess, PID:", proc.pid)
    try:
        # Allow some time for the control room to start
        print("Waiting for 10s, for control room to start")
        time.sleep(10)

        # Check if the subprocess is still running, if not, capture output and raise error
        rc = proc.poll()
        if rc is not None:
            stdout, _ = proc.communicate()
            raise AssertionError(
                f"Subprocess exited early!\nReturn code: {rc}\nOUTPUT:\n{stdout}"
            )

        # Check that all socket-connected modules specified in the config are
        # running and reachable
        for module_name, module_cfg in cfg.get("modules", {}).items():
            if not isinstance(module_cfg, dict):
                continue

            connection_cfg = module_cfg.get("connection")
            if not isinstance(connection_cfg, dict):
                continue
            if connection_cfg.get("type") != "socket":
                continue

            port = int(connection_cfg["port"])
            ip = str(connection_cfg["ip"])
            try:
                print(
                    f"Checking connectivity to module {module_name} at {ip}:{port}..."
                )
                s = socket.create_connection((ip, port), timeout=5)
                s.close()
            except Exception as e:
                raise AssertionError(
                    f"Module {module_name} at {ip}:{port} is not reachable: {e}"
                )

    finally:
        if proc.poll() is None:
            print(f"Terminating control room subprocess {proc.pid} ...")
            proc.send_signal(
                signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
            )

            # Wait for I/O, necessary to ensure proper termination
            stdout, _ = proc.communicate()

            try:
                proc.wait(timeout=20)
            except Exception:
                print(f"Subprocess {proc.pid} did not terminate in time, killing it.")
                proc.kill()
                proc.wait(timeout=20)
                assert False, (
                    "Control room subprocess did not terminate gracefully after signal."
                )

        assert proc.poll() is not None, (
            "Control room subprocess did not shut down properly."
        )

        # Check that socket-connected modules have shut down properly
        for module_name, module_cfg in cfg.get("modules", {}).items():
            if not isinstance(module_cfg, dict):
                continue

            connection_cfg = module_cfg.get("connection")
            if not isinstance(connection_cfg, dict):
                continue
            if connection_cfg.get("type") != "socket":
                continue

            port = int(connection_cfg["port"])
            ip = str(connection_cfg["ip"])
            # Check if the module port is open, it should be closed now
            with pytest.raises(Exception):
                try:
                    conn = socket.create_connection((ip, port), timeout=0.5)
                    conn.close()
                except Exception as e:
                    print(
                        f"Module {module_name} at {ip}:{port} is confirmed shut down."
                    )
                    raise e

        # Check that log server has shut down properly
        log_port = 9020
        with pytest.raises(Exception):
            try:
                conn = socket.create_connection(("127.0.0.1", log_port), timeout=0.5)
                conn.close()
            except Exception as e:
                print(f"Log server at 127.0.0.1:{log_port} is confirmed shut down.")
                raise e
