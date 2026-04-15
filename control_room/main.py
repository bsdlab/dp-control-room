import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
from dareplane_utils.module_handling.communication import SocketCommunicator
from fire import Fire
from waitress.server import create_server

from control_room.callbacks import CallbackBroker
from control_room.gui.app import build_app
from control_room.utils.logging import logger
from control_room.utils.modules import ControlRoomModuleConnection, initialize_modules
from control_room.utils.network import wait_for_port

# --- For backwards compatibility with python < 3.11
try:
    import tomllib

    def toml_load(file: Path):
        return tomllib.load(open(file, "rb"))

except ImportError:
    try:
        import toml

        def toml_load(file: Path):
            return toml.load(open(file, "r"))

    except ImportError:
        raise ImportError(
            "Please install either use python > 3.11 or install `toml` library"
            "to able to parse the config files."
        )


logger.setLevel(10)

SETUP_CFG_PATH: str = "./configs/example_cfg.toml"


def test_dummy(debug: bool = True):
    from tests.resources.tmodule import get_dummy_modules

    cfg = toml_load(Path(SETUP_CFG_PATH))
    modules = get_dummy_modules()
    for m in modules:
        m.get_pcommands()
        m.start_socket_client()
        print(m)

    app = build_app(modules, macros=cfg.get("macros", None))  # type: ignore
    app.run_server(debug=debug)


def close_down_connections(mod_connections: list[ControlRoomModuleConnection]):
    """
    Close all ControlRoomModuleConnection instances.
    """
    for conn in mod_connections:
        conn.stop()


def run_control_room(setup_cfg_path: str = SETUP_CFG_PATH):
    """
    Run the control room application with the given setup configuration.

    This function initializes the control room application, starts the module servers,
    connects clients to the servers, and sets up the callback broker. It also creates
    and runs the Dash app for the GUI.

    Parameters
    ----------
    setup_cfg_path : str, optional
        The path to the setup configuration file. Defaults to `setup_cfg_path`.

    """

    cfg_file = Path(setup_cfg_path).resolve()
    cfg = toml_load(cfg_file)

    connections: list[ControlRoomModuleConnection] = []
    log_server = psutil.Process(
        subprocess.Popen(
            [sys.executable, "-m", "control_room.utils.logserver"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        ).pid
    )
    wait_for_port(port=9020, timeout=5)  # wait for log server to be ready

    logger.info(f"Opening control room with configuration: {setup_cfg_path}")
    cbb_th = None
    cbb_stop = None
    server = None

    try:
        connections = initialize_modules(cfg, cfg_file)

        # start and connect to the modules
        for conn in connections:
            logger.debug(f"Launching and connecting to {conn.name=}")
            conn.start()

        time.sleep(2)  # give the servers a moment to start

        # Get the pcomms for each module
        for conn in connections:
            conn.get_pcommands()

        # hook up the callback broker
        logger.debug("Starting CallbackBroker thread")
        cbb_stop = threading.Event()
        cbb_stop.clear()

        # prepare the connection socket timeouts to be quicker
        for c in connections:
            if (
                c.communicator
                and isinstance(c.communicator, SocketCommunicator)
                and c.communicator.socket_c
            ):
                c.communicator.socket_c.settimeout(0.001)

        cbb = CallbackBroker(
            mod_connections={c.name: c for c in connections},
            stop_event=cbb_stop,
        )
        logger.info(
            f"CallbackBroker has following modules connected: {list(cbb.mod_connections.keys())}"
        )
        cbb_th = threading.Thread(target=cbb.listen_for_callbacks)
        cbb_th.start()

        # Create the dash app
        app = build_app(connections, macros=cfg.get("macros", None))

        # Note: debug True will lead to conflicts with sockets already being used
        # since dash will run the script to this point another time
        # Use the test_dummy for GUI development instead

        # for the debugging Flask server
        # app.run_server(debug=True)

        # for a lightweight production server
        # app.enable_dev_tools(debug=True)

        def on_shutdown():
            """Close down server on shutdown signal, so we can cleanup properly."""
            if server:
                server.close()

        # Register signal handlers for graceful shutdown
        # SIGBREAK is Windows-specific
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda s, f: on_shutdown())  # type: ignore
        signal.signal(signal.SIGINT, lambda s, f: on_shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: on_shutdown())

        logger.info("Serving control room on port 8050")
        server = create_server(app.server, port=8050)
        server.run()

        logger.info("Control room server has stopped.")

    finally:
        logger.info("Shutting down control room...")

        if cbb_th:
            try:
                logger.debug("Stopping callback broker")
                if cbb_stop:
                    cbb_stop.set()
                cbb_th.join(timeout=3)
            except Exception as e:
                logger.error(f"Error while stopping CallbackBroker: {e}")

        logger.debug("Closing down connections")
        try:
            close_down_connections(connections)
        except Exception as e:
            logger.error(f"Error while closing down connections: {e}")

        logger.debug("Terminating log server")
        time.sleep(1)  # give some time to process remaining logs

        # Using prints, as the log server should be down, potentially before the
        # message reaches the server via TCP
        if log_server.is_running():
            try:
                print("Calling log_server.terminate()")
                log_server.terminate()
                log_server.wait(timeout=3)
            except psutil.TimeoutExpired:
                print("TimeoutExpired, calling log_server.kill()")
                log_server.kill()


if __name__ == "__main__":
    Fire(run_control_room)
