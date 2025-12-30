import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import tomllib


def test_run_control_room():
    cfg_path = "./configs/example_cfg.toml"
    cfg = tomllib.load(open(Path(cfg_path), "rb"))

    print("Sys executable:", sys.executable)
    # Start the control room in a subprocess, capturing stdout and stderr so we can debug if it fails
    proc = subprocess.Popen(
        [sys.executable, "-m", "control_room.main", "--setup-cfg-path", cfg_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )

    print("Started control room subprocess, PID:", proc.pid)
    try:
        # Allow some time for the control room to start
        time.sleep(20)

        # Check if the subprocess is still running, if not, capture output and raise error
        rc = proc.poll()
        if rc is not None:
            stdout, stderr = proc.communicate()
            raise AssertionError(
                f"Subprocess exited early!\n"
                f"Return code: {rc}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )

        # Check that all modules specified in the config are running and reachable
        for conn_type in ["python", "exe"]:
            if conn_type in cfg:
                for module_name in cfg[conn_type]["modules"]:
                    port = cfg[conn_type]["modules"][module_name]["port"]
                    ip = cfg[conn_type]["modules"][module_name]["ip"]
                    # Check if the module port is open
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
            stdout, stderr = proc.communicate()

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

        # Check that modules have shut down properly
        for conn_type in ["python", "exe"]:
            if conn_type in cfg:
                for module_name in cfg[conn_type]["modules"]:
                    port = cfg[conn_type]["modules"][module_name]["port"]
                    ip = cfg[conn_type]["modules"][module_name]["ip"]
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
