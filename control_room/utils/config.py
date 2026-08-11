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
    python_key = cfg.get("python", None)
    if python_key:
        modules = cfg["python"].get("modules", None)
        if modules:
            logger.warning(
                "\n" + "-" * 80 + "\n"
                "Starting from control_room 0.1.2 (and dareplane-pyutils 0.0.23) the default configuration for modules changed."
                "Instead of using:\n[python.modules.<my_module>]\nNow use:\n[modules.<my_module>]\nkind='python'"
                "\n\nThe configuration will be transformed automatically to match the new pattern. Update the config to get rid of this message."
                "\n" + "-" * 80 + "\n"
            )

            cfg["modules"] = {m: mcfg | {"kind": "python"} for m, mcfg in modules.items()}

            # modules_root lived under [python] in the legacy convention, but is
            # looked up as modules.modules_root in the new one
            modules_root = python_key.get("modules_root", None)
            if modules_root:
                cfg["modules"]["modules_root"] = modules_root

            del cfg["python"]

            logger.warning("Created the following configs for modules:\n" + str(cfg))

    return cfg


if __name__ == "__main__":
    cfg_file = Path("./tests/resources/test_legacy_cfg.toml").resolve()
    cfg = toml_load(cfg_file)
