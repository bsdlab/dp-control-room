import time
from pathlib import Path

import pytest

from control_room.utils.config import check_and_transform_legacy_cfg, toml_load
from control_room.utils.modules import initialize_modules

CFG_PATH = Path("./tests/resources/test_cfg.toml")


@pytest.fixture()
def connection():
    cfg = check_and_transform_legacy_cfg(toml_load(CFG_PATH))
    conn = initialize_modules(cfg, CFG_PATH.resolve())[0]
    yield conn
    try:
        conn.stop()
    except Exception:
        pass


def test_is_up_reflects_module_state(connection):
    """The UP check must discriminate between a running and a stopped module."""
    assert connection.is_up() is False, (
        "Module should not be reported as up before it is started"
    )

    connection.start()
    time.sleep(3)
    assert connection.is_up() is True, "Running module should be reported as up"

    # repeated calls must stay stable, i.e. not consume a required reply
    assert connection.is_up() is True, "Repeated UP checks should stay consistent"

    connection.stop()
    time.sleep(2)
    assert connection.is_up() is False, (
        "Module should not be reported as up after it was stopped"
    )


def test_is_up_without_communicator(connection):
    """A connection without a communicator is down, not an exception."""
    connection.communicator = None
    assert connection.is_up() is False


def test_up_check_does_not_break_pcomms(connection):
    """The UP round trip must not interfere with the GET_PCOMMS round trip."""
    connection.start()
    time.sleep(3)

    connection.get_pcommands()
    before = list(connection.pcomms)
    assert before, "Expected pcomms to be populated for a running module"

    assert connection.is_up() is True

    connection.get_pcommands()
    assert list(connection.pcomms) == before, (
        "pcomms should be unchanged by an interleaved UP check"
    )
