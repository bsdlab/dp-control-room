import logging
from pathlib import Path

import pytest

from control_room.utils.config import check_and_transform_legacy_cfg, toml_load

LEGACY_CFG_PATH = Path("./tests/") / "resources" / "test_legacy_cfg.toml"


@pytest.fixture()
def legacy_cfg():
    return toml_load(LEGACY_CFG_PATH)


def test_legacy_cfg_logs_warning(legacy_cfg, caplog):
    with caplog.at_level(logging.WARNING, logger="control_room"):
        check_and_transform_legacy_cfg(legacy_cfg)

    assert any("0.1.2" in msg for msg in caplog.messages), (
        "Expected deprecation warning mentioning version 0.1.2 to be logged"
    )


def test_legacy_cfg_transforms_modules(legacy_cfg):
    result = check_and_transform_legacy_cfg(legacy_cfg)

    assert "modules" in result, "Expected top-level 'modules' key after transform"

    for name, module_cfg in result["modules"].items():
        assert isinstance(module_cfg, dict), f"Module {name!r} config should be a dict"
        assert module_cfg.get("kind") == "python", (
            f"Module {name!r} should have kind='python' after legacy transform"
        )

    original_modules = toml_load(LEGACY_CFG_PATH)["python"]["modules"]
    assert set(result["modules"].keys()) == set(original_modules.keys()), (
        "All module keys from legacy config should be preserved"
    )

    for name, orig in original_modules.items():
        for key, value in orig.items():
            assert result["modules"][name][key] == value, (
                f"Module {name!r} field {key!r} should be preserved unchanged"
            )


def test_non_legacy_cfg_is_unchanged():
    cfg = {
        "modules": {
            "my-module": {"kind": "python", "port": 8080},
        }
    }
    result = check_and_transform_legacy_cfg(cfg)
    assert result == cfg
