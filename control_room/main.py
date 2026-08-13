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
from waitress import wasyncore
from waitress.server import create_server

from control_room.callbacks import CallbackBroker
from control_room.gui.app import build_app
from control_room.utils.logging import logger
from control_room.utils.modules import ControlRoomModuleConnection, initialize_modules
from control_room.utils.network import wait_for_port
from control_room.utils.config import check_and_transform_legacy_cfg

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
            "Please install Python > 3.11 or install `toml` library"
            "to able to parse the config files."
        )


logger.setLevel(10)

SETUP_CFG_PATH: str = "./configs/example_cfg.toml"


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

    cfg = check_and_transform_legacy_cfg(cfg)

    log_server = psutil.Process(
        subprocess.Popen(
            [sys.executable, "-m", "control_room.utils.logserver"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        ).pid
    )
    wait_for_port(port=9020, timeout=5)  # wait for log server to be ready

    logger.info(f"Opening control room with configuration: {setup_cfg_path}")
    shutdown_requested = threading.Event()

    cbb_th: threading.Thread | None = None  # used in the finally

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
        # daemon, so a hanging broker can never keep the interpreter alive
        cbb_th = threading.Thread(target=cbb.listen_for_callbacks, daemon=True)
        cbb_th.start()

        # Create the dash app
        app = build_app(connections, macros=cfg.get("macros", None))

        logger.info("Serving control room on port 8050")
        server = create_server(app.server, port=8050)

        def on_shutdown(*args):
            """Request shutdown from within a signal handler.

            Only a flag is set here and the asyncore loop is woken up. Closing
            the sockets directly from the handler would pull them away from the
            `select()` call the loop is blocked in, which raises an `OSError`.
            The actual closing is done on the main thread once `run()` returned.
            """
            logger.info("Shutdown signal received, stopping the server ...")
            shutdown_requested.set()
            try:
                # wakes up the `select()` of the asyncore loop
                server.trigger.pull_trigger()
            except Exception as e:
                logger.error(f"Error while waking up the server loop: {e}")

        # Register signal handlers for graceful shutdown
        # SIGBREAK is Windows-specific and is what CTRL+Break sends
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, on_shutdown)  # type: ignore
        signal.signal(signal.SIGINT, on_shutdown)
        signal.signal(signal.SIGTERM, on_shutdown)

        # `run()` blocks until the socket map is empty, so it is driven here in
        # steps to be able to react to a shutdown request in between
        while not shutdown_requested.is_set():
            try:
                wasyncore.loop(
                    timeout=0.5,
                    map=server._map,
                    count=1,
                    use_poll=server.adj.asyncore_use_poll,
                )
            except KeyboardInterrupt:
                # On Windows the KeyboardInterrupt can surface here instead of
                # the signal handler being run to completion
                shutdown_requested.set()
            except OSError as e:
                logger.debug(f"Server loop stopped with: {e}")
                break

        logger.debug("Closing server sockets")
        try:
            wasyncore.close_all(server._map, ignore_all=True)
        except Exception as e:
            logger.error(f"Error while closing server sockets: {e}")

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
