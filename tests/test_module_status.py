import logging
import threading
import time
from pathlib import Path

import pytest

from control_room.callbacks import CallbackBroker
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


@pytest.mark.parametrize(
    "msg, expected",
    [
        (b"1", b""),  # pure UP acknowledgement
        (b"11", b""),  # several acknowledgements batched together
        (b"dp-mod|START|{}", b"dp-mod|START|{}"),  # plain callback
        (b"1dp-mod|START|{}", b"dp-mod|START|{}"),  # ack prepended to a callback
        (b"dp-mod|START|{}1", b"dp-mod|START|{}"),  # ack appended to a callback
        (b"dp-mod|START|{'a': 1}", b"dp-mod|START|{'a': 1}"),  # 1 inside the payload
        (b"mod1|START|{}", b"mod1|START|{}"),  # module name ending in 1
    ],
)
def test_up_acks_are_stripped_but_callbacks_survive(msg, expected):
    """`1` is a liveness ack, but must not corrupt real callback messages."""
    cbb = CallbackBroker(mod_connections={})
    assert cbb._consume_up_acks(msg, "some-mod") == expected


def test_up_ack_is_not_routed_as_callback(connection, caplog):
    """The UP reply must not be mistaken for a callback while the broker runs."""
    connection.start()
    time.sleep(3)
    connection.get_pcommands()

    # mimic main.py: tight socket timeout plus a broker on the same socket
    connection.communicator.socket_c.settimeout(0.001)
    stop = threading.Event()
    cbb = CallbackBroker(mod_connections={connection.name: connection}, stop_event=stop)
    th = threading.Thread(target=cbb.listen_for_callbacks, daemon=True)
    th.start()

    try:
        with caplog.at_level(logging.ERROR, logger="control_room"):
            results = [connection.is_up() for _ in range(5)]
    finally:
        stop.set()
        th.join(timeout=3)

    assert all(results), (
        "Module should be reported as up while the CallbackBroker is running"
    )
    assert not [m for m in caplog.messages if "CallbackBroker requires messages" in m], (
        "The UP acknowledgement must not be processed as a callback PCOMM"
    )


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
