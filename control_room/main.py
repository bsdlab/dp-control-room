import subprocess
import sys
import threading
import time
import os
from pathlib import Path
import signal
import psutil
from fire import Fire
from waitress.server import create_server

from control_room.callbacks import CallbackBroker
from control_room.connection import ModuleConnection, ModuleConnectionExe
from control_room.gui.app import build_app
from control_room.utils.logging import logger
from tests.resources.tmodule import get_dummy_modules

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

setup_cfg_path: str = "./configs/example_cfg.toml"


def test_dummy(debug: bool = True):
    cfg = toml_load(setup_cfg_path)
    modules = get_dummy_modules()
    for m in modules:
        m.get_pcommands()
        m.start_socket_client()
        print(m)

    app = build_app(modules, macros=cfg.get("macros", None))
    app.run_server(debug=debug)


def initialize_python_modules(mod_cfgs: dict) -> list[ModuleConnection]:
    """
    Initialize Python modules based on the provided configurations.
    """
    connections = []

    if "modules" not in mod_cfgs:
        logger.info("No python modules to initialize.")
        return connections

    if "modules_root" not in mod_cfgs:
        logger.warning(
            "No 'modules_root' specified in python module configurations. "
            f"Using parent directory of current working directory as default ({Path.cwd().parent})."
        )
        mod_cfgs["modules_root"] = Path.cwd().parent

    logger.debug(f"Python module configurations found: {mod_cfgs['modules'].keys()}")

    # Python modules
    for module_name, module_cfg in mod_cfgs["modules"].items():
        connections.append(
            ModuleConnection(
                name=module_name,
                module_root_path=Path(mod_cfgs["modules_root"]),
                **module_cfg,
            )
        )

    return connections


def initialize_exe_modules(mod_cfgs: dict) -> list[ModuleConnection]:
    """
    Initialize modules provided with an executable target. NOT WORKING ATM.
    """
    connections = []

    if "modules" not in mod_cfgs:
        logger.info("No exe modules to initialize.")
        return connections

    logger.debug(f"Exe module configurations found: {mod_cfgs['modules'].keys()}")

    # Exe modules
    for module_name, module_cfg in mod_cfgs["modules"].items():
        required_keys = ["path", "ip", "port", "pcomms"]
        for key in required_keys:
            if key not in module_cfg:
                raise KeyError(
                    f"Module configuration for {module_name} is missing required key: {key}"
                )

        connections.append(
            ModuleConnectionExe(
                name=module_name,
                exe_path=Path(module_cfg["path"]),
                ip=module_cfg["ip"],
                port=module_cfg["port"],
                pcomms=list(module_cfg["pcomms"].keys()),
                pcomms_defaults=module_cfg["pcomms"],
            )
        )

    return connections


def close_down_connections(mod_connections: list[ModuleConnection]):
    """
    Close all ModuleConnection instances.
    """
    # Close down
    for conn in mod_connections:
        if conn.socket_c:
            # API connection
            conn.stop_socket_c()

        # the server process
        if conn.host_process:
            conn.stop_process()


def run_control_room(setup_cfg_path: str = setup_cfg_path):
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

    cfg = toml_load(Path(setup_cfg_path))

    connections = []
    log_server = psutil.Process(
        subprocess.Popen([sys.executable, "-m", "control_room.utils.logserver"], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0).pid
    )

    time.sleep(0.5)  # give the log server a moment to start

    logger.info(f"Opening control room with configuration: {setup_cfg_path}")
    cbb_th = None
    server = None

    try:
        # Other modules
        if "exe" in cfg.keys():
            connections += initialize_exe_modules(cfg["exe"])

        if "python" in cfg.keys():
            connections += initialize_python_modules(cfg["python"])

        # start the module servers - spawning the processes
        for conn in connections:
            logger.debug(f"Starting module server for {conn.name=}")
            conn.start_module_server()

        time.sleep(2)  # give the servers a moment to start

        # connect clients to the servers
        for conn in connections:
            logger.debug(f"Starting socket client for {conn.name=}")
            conn.start_socket_client()

            logger.debug(f"Getting PCOMMS for {conn.name=}")
            # request primary commands
            conn.get_pcommands()

        # hook up the callback broker
        logger.debug("Starting CallbackBroker thread")
        cbb_stop = threading.Event()
        cbb_stop.clear()

        # prepare the connection socket timeouts to be quicker
        for c in connections:
            c.socket_c.settimeout(0.001)

        cbb = CallbackBroker(
            mod_connections={c.name: c for c in connections},
            stop_event=cbb_stop,
        )
        logger.info(
            f"CallbackBroker has following modules connected: {list[cbb.mod_connections.keys()]}"
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
        # TODO: test on all platforms
        signal.signal(signal.SIGBREAK, lambda s,f: on_shutdown())
        signal.signal(signal.SIGINT, lambda s,f: on_shutdown())
        signal.signal(signal.SIGTERM, lambda s,f: on_shutdown())

        logger.info("Serving control room on port 8050")
        server = create_server(app.server, port=8050)
        server.run()
        
        logger.info("Control room server has stopped.")

    finally:
        logger.info("Shutting down control room...")

        if cbb_th:
            try:
                logger.debug("Stopping callback broker")
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
        time.sleep(1) # give some time to process remaining logs

        if log_server.is_running():
            try:
                log_server.terminate()
                log_server.wait(3)
            except psutil.TimeoutExpired:
                log_server.kill()


if __name__ == "__main__":
    Fire(run_control_room)
