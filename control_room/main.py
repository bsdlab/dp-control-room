import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import psutil
from dareplane_utils.module_handling.communication import SocketCommunicator
from dareplane_utils.module_handling.launcher import ExeLauncher, PythonLauncher
from dareplane_utils.module_handling.module_connection import ModuleConnection
from fire import Fire
from waitress.server import create_server

from control_room.callbacks import CallbackBroker
from control_room.gui.app import build_app
from control_room.utils.logging import logger
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


def _resolve_cfg_path(path_value: str, cfg_file: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()

    cfg_relative = (cfg_file.parent / path).resolve()
    if cfg_relative.exists():
        return cfg_relative

    cwd_relative = (Path.cwd() / path).resolve()
    if cwd_relative.exists():
        return cwd_relative

    raise FileNotFoundError(
        f"Cannot resolve path '{path_value}' in config file '{cfg_file}'. "
    )


def _get_required_field(dict, key) -> Any:
    if key not in dict:
        raise KeyError(f"Missing required key '{key}' in {dict}")
    return dict[key]


def initialize_modules(cfg: dict[str, Any], cfg_file: Path) -> list[ModuleConnection]:
    connections: list[ModuleConnection] = []

    modules_cfg = cfg.get("modules", {})
    if not isinstance(modules_cfg, dict):
        raise TypeError("Config key 'modules' must be a table/object")

    modules_root = modules_cfg.get("modules_root", None)
    modules = [m for m in modules_cfg.items() if isinstance(m[1], dict)]  # type: ignore

    for module_key, module_cfg in modules:
        module_kind = _get_required_field(module_cfg, "kind").strip().lower()
        name = str(module_cfg.get("name", module_key))

        if module_kind == "python":
            entry_point = str(
                module_cfg.get("module", f"{module_key.replace('-', '_')}.main")
            )

            if "cwd" in module_cfg:
                cwd = _resolve_cfg_path(str(module_cfg["cwd"]), cfg_file)
            elif modules_root:
                cwd = _resolve_cfg_path(
                    str(Path(str(modules_root)) / module_key), cfg_file
                )
            else:
                raise KeyError(
                    f"Missing 'cwd' for modules.{module_key}. "
                    "Either set module-specific 'cwd' or global 'modules.modules_root'."
                )

            launcher = PythonLauncher(
                entry_point=entry_point,
                cwd=cwd,
                executable=str(module_cfg.get("python_executable", sys.executable)),
                args=list(module_cfg.get("args", [])),
                kwargs=dict(module_cfg.get("kwargs", {})),
            )
        elif module_kind == "exe":
            exe_path = _resolve_cfg_path(
                _get_required_field(module_cfg, "path"), cfg_file
            )
            exe_cwd = (
                _resolve_cfg_path(str(module_cfg["cwd"]), cfg_file)
                if "cwd" in module_cfg
                else None
            )

            launcher = ExeLauncher(
                exe_path=exe_path,
                args=list(module_cfg.get("args", [])),
                cwd=exe_cwd,
            )
        else:
            raise ValueError(
                f"Unsupported kind '{module_kind}' for modules.{module_key}. "
                "Supported kinds: 'python', 'exe'."
            )

        connection_cfg = module_cfg.get("connection")
        if connection_cfg and connection_cfg.get("type") == "socket":
            ip = str(_get_required_field(connection_cfg, "ip"))
            port = int(_get_required_field(connection_cfg, "port"))
            retry_after_s = float(connection_cfg.get("retry_after_s", 1.0))
            max_connect_retries = int(connection_cfg.get("max_connect_retries", 3))
            communicator = SocketCommunicator(
                ip=ip,
                port=port,
                name=name,
                retry_after_s=retry_after_s,
                max_connect_retries=max_connect_retries,
                logger=logger,
            )
        elif module_cfg.get("connection", None) is None:
            communicator = None
        else:
            raise ValueError(
                f"Unsupported connection type for modules.{module_key}. "
                "Currently only 'socket' connection is supported."
            )

        connections.append(
            ModuleConnection(
                name=name,
                launcher=launcher,
                communicator=communicator,
                pcomms=list(module_cfg.get("pcomms", [])),
            )
        )

    return connections


def close_down_connections(mod_connections: list[ModuleConnection]):
    """
    Close all ModuleConnection instances.
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

    connections: list[ModuleConnection] = []
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

        # connect clients to the servers
        for conn in connections:
            if not conn.pcomms:
                logger.debug(f"Getting PCOMMS for {conn.name=}")
                conn.get_pcommands()

        # hook up the callback broker
        logger.debug("Starting CallbackBroker thread")
        cbb_stop = threading.Event()
        cbb_stop.clear()

        # prepare the connection socket timeouts to be quicker
        for c in connections:
            if c.socket_c:
                c.socket_c.settimeout(0.001)

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
