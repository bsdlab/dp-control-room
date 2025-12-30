import logging
import subprocess
import sys
import time
from socket import socket

import pytest
from dareplane_utils.logging.logger import get_logger
from dareplane_utils.logging.ujson_socket_handler import UJsonSocketHandler

from tests.resources.helpers import wait_for_port


@pytest.fixture()
def fresh_logger():
    """Provide a fresh logger instance for each test with a new UJsonSocketHandler.

    This fixture ensures that the logger used in tests has a fresh UJsonSocketHandler.
    Usually, loggers share the handler instance, which can lead to interference between tests.

    Yields
    ------
    logging.Logger
    """
    fresh_logger = get_logger("test_logger")
    for handler in fresh_logger.handlers[:]:
        if isinstance(handler, UJsonSocketHandler):
            # Remove existing UJsonSocketHandler
            fresh_logger.removeHandler(handler)

    # Add a new UJsonSocketHandler, pointing to the test log server
    fresh_logger.addHandler(UJsonSocketHandler("127.0.0.1", 9020))

    fresh_logger.setLevel(logging.DEBUG)
    yield fresh_logger


def test_logger_fails_fast(fresh_logger):
    logger = fresh_logger
    test_socket = socket()
    test_socket.settimeout(1)

    # Ensure the log server is not running
    with pytest.raises(Exception):
        test_socket.connect(("127.0.0.1", 9020))

    start = time.time()
    logger.debug("Testing logger fails fast on unreachable server")
    end = time.time()

    # If the log server is unreachable, the logger should fail fast
    # The timeout duration is currently defined as 0.3s in dareplane-pyutils/src/dareplane_utils/logging/ujson_socket_handler.py
    assert end - start < 0.4

    start = time.time()
    logger.debug("Testing continued logging after failed connection")
    end = time.time()

    # The socket connection uses an exponential backoff, so subsequent calls within a short time should fail immediately
    assert end - start < 0.01


def test_log_server_socket_connection():
    # Start the log server process (example command)
    proc = subprocess.Popen(
        [sys.executable, "-m", "control_room.utils.logserver"],
    )

    # Try to connect to the log server, fails if not able to connect within timeout
    wait_for_port("127.0.0.1", 9020, timeout=5.0)

    # Teardown
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_logger_logs(fresh_logger):
    logger = fresh_logger
    proc = subprocess.Popen(
        [sys.executable, "-m", "control_room.utils.logserver"],
    )

    # Wait for the log server to be ready
    wait_for_port("127.0.0.1", 9020, timeout=5.0)

    # try logging
    start = time.time()
    logger.debug("This is test debug message from test_logger")
    end = time.time()

    # With the log server running, logging should be quick
    assert end - start < 0.1

    # Teardown
    time.sleep(
        1.0
    )  # give some time for the log to be processed, log does not show up otherwise
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
