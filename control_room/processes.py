import os
import subprocess
import time
from pathlib import Path
from sys import executable

import psutil

from control_room.utils.logging import logger

# Used to separate multiple shell commands in one string
COMMAND_SEP_MAP = {
    "darwin": ";",
    "win32": "&",
    "linux": ";",
    "linux2": ";",
}


def close_child_processes(process: subprocess.Popen) -> int:
    """Close all child processes of a Popen instance"""
    logger.debug(f"Closing child processes of parent process={process.pid}")
    try:
        parent_ps = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        logger.debug(f"Parent process {process.pid} no longer existing")
        return 0

    max_iter = 5
    i = 0

    while i <= max_iter:
        if i > 0:
            time.sleep(0.2)
        try:
            children = parent_ps.children()
        except psutil.NoSuchProcess:
            logger.debug(f"Parent process {process.pid} no longer existing")
            # Parent process is gone, so we are done
            return 0

        # If no children, break
        if children == []:
            break

        # Otherwise, try to terminate children
        for ch in children:
            try:
                logger.debug(f"Sending terminate to child process={ch}")
                ch.terminate()
            except psutil.NoSuchProcess:
                logger.debug(f"Child process {ch.pid} no longer existing")
        i += 1

    logger.debug(f"Sending kill to parent process={parent_ps}")
    try:
        parent_ps.kill()
        parent_ps.wait()  # wait for the transition from zombie to terminated
    except psutil.NoSuchProcess:
        logger.debug(f"Parent process {process.pid} no longer existing")

    return 0


def start_container(
    module_name: str,
    ip: str,
    port: int,
    loglevel: int = 10,
    modules_root_path: Path = Path("."),
    start_kwargs: dict = {},
) -> subprocess.Popen:
    """
    Start a container for a given module.

    This function creates a subprocess to run a specified module using the provided
    configurations. It supports starting Python modules and can be extended to support
    other types of containers in the future.

    Parameters
    ----------
    module_name : str
        The name of the module to start.
    ip : str
        The IP address on which the module should run.
    port : int
        The port number on which the module should run.
    loglevel : int, optional
        The logging level for the module, by default 10 (DEBUG).
    modules_root_path : Path, optional
        The root path where the modules are located, by default Path(".").
    start_kwargs : dict, optional
        Additional keyword arguments to pass to the module, by default {}.

    Returns
    -------
    subprocess.Popen
        A Popen object representing the started subprocess.

    Raises
    ------
    AssertionError
        If the specified module path does not exist.
    """

    modpath = modules_root_path.joinpath(module_name)
    assert modpath.exists(), f"not a valid path {modpath}"

    logger.info(f"Spawning {module_name=} @ {ip}:{port} with {start_kwargs=}")

    cmd = [
        executable,
        "-m",
        "api.server",
        f"--port={port}",
        f"--ip={ip}",
        f"--loglevel={loglevel}",
        *[f"--{k}={v}" for k, v in start_kwargs.items()],
    ]

    # Explicitly forward the environment so that DYLD_LIBRARY_PATH (macOS),
    # LD_LIBRARY_PATH (Linux) and PYTHONPATH survive the grandchild spawn.
    # On macOS, SIP strips DYLD_LIBRARY_PATH from grandchild processes unless
    # it is set explicitly in the env dict passed to Popen.
    env = os.environ.copy()

    logger.debug(f"Running Popen with {cmd=}")
    return subprocess.Popen(
        cmd,
        cwd=str(modpath.resolve()),
        env=env,
    )
