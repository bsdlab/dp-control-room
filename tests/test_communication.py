import pytest
import psutil
import threading

from tests.resources.tserver import run_server
from control_room.connection import ModuleConnection
from control_room.utils.logging import logger
from tests.resources.tmodule import start_container

logger.setLevel(10)


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
    assert tuple(con.pcomms) == ("START", "GET_PCOMMS")


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

    # Second condition added for testing on windows
    assert con.host_process is None or not psutil.pid_exists(host_pid)

    logger.info(f"{hostp=}")


# def test_just_run():
#     run_server(port=8080, ip="127.0.0.1")
