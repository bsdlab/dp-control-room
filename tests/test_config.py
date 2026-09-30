import logging
from pathlib import Path

import pytest

from control_room.utils.config import check_and_transform_legacy_cfg, toml_load
from control_room.utils.modules import initialize_modules

RESOURCES = Path("./tests/") / "resources"
LEGACY_CFG_PATH = RESOURCES / "test_legacy_cfg.toml"
CFG_PATH = RESOURCES / "test_cfg.toml"
LEGACY_MOCKUP_CFG_PATH = RESOURCES / "test_legacy_mockup_cfg.toml"


@pytest.fixture()
def legacy_cfg():
    return toml_load(LEGACY_CFG_PATH)


def test_legacy_cfg_logs_warning(legacy_cfg, caplog, monkeypatch):
    # control_room's logger has propagate=False (set by dareplane_utils.get_logger)
    # so records never reach caplog's root-logger handler unless we re-enable it here.
    monkeypatch.setattr(logging.getLogger("control_room"), "propagate", True)

    with caplog.at_level(logging.WARNING, logger="control_room"):
        check_and_transform_legacy_cfg(legacy_cfg)

    assert any("0.1.2" in msg for msg in caplog.messages), (
        "Expected deprecation warning mentioning version 0.1.2 to be logged"
    )


def test_legacy_cfg_transforms_modules(legacy_cfg):
    result = check_and_transform_legacy_cfg(legacy_cfg)

    assert "modules" in result, "Expected top-level 'modules' key after transform"

    # scalar siblings such as modules_root are not module tables
    result_modules = {k: v for k, v in result["modules"].items() if isinstance(v, dict)}

    for name, module_cfg in result_modules.items():
        assert module_cfg.get("kind") == "python", (
            f"Module {name!r} should have kind='python' after legacy transform"
        )

    original_modules = toml_load(LEGACY_CFG_PATH)["python"]["modules"]
    assert set(result_modules.keys()) == set(original_modules.keys()), (
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


def test_legacy_cfg_preserves_modules_root(legacy_cfg):
    """modules_root moves from [python] to modules.modules_root."""
    result = check_and_transform_legacy_cfg(legacy_cfg)

    assert result["modules"]["modules_root"] == "../../", (
        "modules_root must be carried over to 'modules', otherwise every python "
        "module fails to resolve its cwd"
    )
    assert "python" not in result, (
        "The legacy 'python' key should be removed after the transform"
    )


def _describe(connections):
    """Reduce connections to the fields that define the launch/connection setup."""
    return {
        c.name: (
            c.launcher.entry_point,
            c.launcher.cwd,
            c.launcher.args,
            c.launcher.kwargs,
            c.communicator.ip,
            c.communicator.port,
            c.communicator.retry_after_s,
            c.communicator.max_connect_retries,
        )
        for c in connections
    }


@pytest.mark.parametrize("cfg_path", [CFG_PATH, LEGACY_MOCKUP_CFG_PATH])
def test_both_conventions_initialize_modules(cfg_path):
    """Both [modules.<name>] and [python.modules.<name>] must yield usable modules."""
    cfg = check_and_transform_legacy_cfg(toml_load(cfg_path))
    connections = initialize_modules(cfg, cfg_path.resolve())

    assert [c.name for c in connections] == ["dp-mockupmodule"]
    assert connections[0].launcher.cwd == (RESOURCES / "dp-mockupmodule").resolve()


def test_legacy_and_new_convention_are_equivalent():
    """The legacy config must parse into the same setup as its new-convention twin."""
    new = initialize_modules(
        check_and_transform_legacy_cfg(toml_load(CFG_PATH)), CFG_PATH.resolve()
    )
    legacy = initialize_modules(
        check_and_transform_legacy_cfg(toml_load(LEGACY_MOCKUP_CFG_PATH)),
        LEGACY_MOCKUP_CFG_PATH.resolve(),
    )

    assert _describe(legacy) == _describe(new)
