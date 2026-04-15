import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dareplane_utils.module_handling.communication import SocketCommunicator
from dareplane_utils.module_handling.launcher import ExeLauncher, PythonLauncher
from dareplane_utils.module_handling.module_connection import ModuleConnection

from control_room.utils.logging import logger


@dataclass
class ControlRoomModuleConnection(ModuleConnection):
    """ModuleConection subclass that adds dp-specific functions such as getting pcomms."""

    pcomms: list[str] = field(default_factory=list)

    def get_pcommands(self) -> None:
        try:
            if not self.communicator:
                logger.warning(
                    f"Cannot get pcomms for {self.name} because it has no communicator"
                )
                return
            self.communicator.send(b"GET_PCOMMS")
            time.sleep(0.1)
            msg = self.communicator.receive(2048 * 8)
            decoded = msg.decode().strip()
            if decoded:
                self.pcomms = decoded.split("|")
        except TimeoutError:
            logger.warning(f"Timeout while getting pcomms for {self.name}")
        except UnicodeDecodeError:
            logger.error(f"Failed to decode pcomms response for {self.name}")
        except Exception as e:
            logger.error(f"Failed to get pcomms for {self.name}: {e}")


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


def initialize_modules(
    cfg: dict[str, Any], cfg_file: Path
) -> list[ControlRoomModuleConnection]:
    connections: list[ControlRoomModuleConnection] = []

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
            ControlRoomModuleConnection(
                name=name,
                launcher=launcher,
                communicator=communicator,
            )
        )
    return connections


if __name__ == "__main__":
    pass
