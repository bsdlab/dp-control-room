import subprocess
import sys
import threading
import time
from typing import Iterator

import psutil
import pytest

from control_room.connection import ModuleConnection
from control_room.utils.logging import logger
from tests.resources.helpers import wait_for_port
from tests.resources.tmodule import start_container
from tests.resources.tserver import run_server, run_slow_startup_server

logger.setLevel(10)


@pytest.fixture(scope="module", autouse=True)
def log_server():
    """
    Start the logging server before running tests and stop it afterward.
    This fixture has module scope and is set to autouse, so it is shared for all tests in the module
    and it automatically runs without being imported.
    """

    # Start the log server process (example command)
    proc = subprocess.Popen(
        [sys.executable, "-m", "control_room.utils.logserver"],
    )

    # Wait for the log server to be ready
    try:
        wait_for_port()
    except TimeoutError as e:
        proc.terminate()
        raise RuntimeError("Log server failed to start") from e

    # Yields to the tests, not used
    yield proc

    # Teardown
    time.sleep(1)  # wait a bit to ensure all logs are sent
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def module_with_thread_for_tserver():
    # setup
    sev = threading.Event()
    thread = threading.Thread(
        target=run_server,
        kwargs=dict(ip="127.0.0.1", port=5050, stop_event=sev),
    )
    thread.start()

    con = ModuleConnection(name="test", ip="127.0.0.1", port=5050)

    con.start_socket_client()

    # The test
    yield con

    # Teardown of threads
    logger.debug("Starting thread teardown")
    con.socket_c.sendall(b"CLOSE\r\n")
    con.stop_socket_c()

    logger.debug("Starting thread teardown")
    thread.join()


def test_socket_connection(module_with_thread_for_tserver):
    con = module_with_thread_for_tserver
    con.get_pcommands()
    assert tuple(con.pcomms) == ("START", "GET_PCOMMS", "STOP", "CLOSE")


@pytest.fixture
def slow_server_thread() -> Iterator[tuple[threading.Thread, threading.Event]]:
    sev = threading.Event()
    thread = threading.Thread(
        target=run_slow_startup_server,
        kwargs=dict(ip="127.0.0.1", port=5051, stop_event=sev),
    )

    yield thread, sev

    sev.set()
    thread.join()


def test_retry_connection_after_s_for_slow_startup(slow_server_thread):
    thread, sev = slow_server_thread
    thread.start()

    # Quick connection should fail
    with pytest.raises(OSError):
        conq = ModuleConnection(
            name="test_slow", ip="127.0.0.1", port=5051, retry_connection_after_s=0.3
        )
        conq.start_socket_client()

    # slow start-up takes 5 seconds -> 3 seconds for retry with 3 retries should be enough
    con = ModuleConnection(
        name="test_slow", ip="127.0.0.1", port=5051, retry_connection_after_s=3
    )

    con.start_socket_client()

    con.get_pcommands()

    time.sleep(0.5)  # wait a bit to ensure response arrived

    # Close before assert could break the test
    con.socket_c.sendall(b"CLOSE\r\n")
    con.stop_socket_c()

    assert "SLOWSERVERTEST" in con.pcomms, (
        f"Did not get the expected pcomms from the server - {con.pcomms=}"
    )


@pytest.fixture
def module_connection_with_running_process():
    # setup
    con = ModuleConnection(
        name="test",
        ip="127.0.0.1",
        port=5051,
        container_starter=start_container,
    )

    con.start_module_server()

    # testing
    yield con

    # teardown
    con.stop_process()
    try:
        host_pid = con.host_process.pid
        hostp = psutil.Process(host_pid)
        hostp.kill()

    except (psutil.NoSuchProcess, AttributeError):
        logger.debug(f"Process {con.host_process=} already killed?")


def test_subprocess(module_connection_with_running_process):
    con = module_connection_with_running_process

    assert con.host_process is not None
    host_pid = con.host_process.pid
    hostp = psutil.Process(host_pid)

    con.stop_process()
    time.sleep(0.5)

    assert con.host_process is None

    # Process should be killed already, so this should raise NoSuchProcess error
    with pytest.raises(psutil.NoSuchProcess):
        hostp.kill()
