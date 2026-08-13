# utilities for validating and parsing config files
from pathlib import Path
from control_room.utils.logging import logger

SETUP_CFG_PATH: str = "./configs/example_cfg.toml"

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


def check_and_transform_legacy_cfg(cfg: dict):
    python_cfgs = cfg.get("python", None)
    exe_cfgs = cfg.get("exe", None)
    warned: bool = False

    new_cfg: dict = {"modules": {}}
    for per_type_cfgs in [exe_cfgs, python_cfgs]:
        if per_type_cfgs is None:
            continue
        modules = per_type_cfgs.get("modules", None)
        modules_root = per_type_cfgs.get("modules_root", None)

        if modules and not warned:
            logger.warning(
                "\n" + "-" * 80 + "\n"
                "Starting from control_room 0.1.2 (and dareplane-pyutils 0.0.23) the default configuration for modules changed."
                "Instead of using:\n[python.modules.<my_module>]\nNow use:\n[modules.<my_module>]\nkind='python'"
                "\n\nThe configuration will be transformed automatically to match the new pattern. Update the config to get rid of this message."
                "\n" + "-" * 80 + "\n"
            )
            warned = True

        # In the legacy config only the python modules were initiated from the control room
        # everything else, including the exe modules was connection only
        kind = "python" if per_type_cfgs == python_cfgs else "conn_only"
        new_cfg["modules"] |= {m: mcfg | {"kind": kind} for m, mcfg in modules.items()}

        # modules_root lived under [python] in the legacy convention, but is
        # looked up as modules.modules_root in the new one
        if modules_root:
            new_cfg["modules"]["modules_root"] = modules_root

    return new_cfg


if __name__ == "__main__":
    cfg_file = Path("./tests/resources/test_legacy_cfg.toml").resolve()
    cfg = toml_load(cfg_file)
