# A server implementation for testing purposes only
import threading
import time

from dareplane_utils.default_server.server import DefaultServer
from fire import Fire

from control_room.utils.logging import logger


def test_print() -> int:
    logger.info("STARTING PRESSED")
    return 0


def run_server(
    port: int = 8080,
    ip: str = "127.0.0.1",
    loglevel: int = 10,
    stop_event: threading.Event = threading.Event(),
):
    logger.setLevel(loglevel)

    pcommand_map = {
        "START": test_print,
        "GET_PCOMMS": "START|INIT|STOP|RUN_BLOCK",
    }

    server = DefaultServer(port, ip=ip, pcommand_map=pcommand_map, name="mockup_module")

    # initialize to start the socket
    server.init_server(stop_event=stop_event)
    # start processing of the server
    server.start_listening()

    return 0


if __name__ == "__main__":
    logger.setLevel(10)
    Fire(run_server)
