from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "exopy_config.toml"
DEFAULT_PERSISTENT_DATA_DIR = ".exopy"


@dataclass(frozen=True, slots=True)
class ExoPyConfig:
    """Global ExoPy configuration loaded from ``exopy_config.toml``."""

    persistent_data_dir: Path
    dace_rc_config_path: Path | None = None


def load_config(start_dir: Path | str | None = None) -> ExoPyConfig:
    """Load ExoPy configuration from the working tree or return defaults."""
    root = Path(start_dir) if start_dir is not None else Path.cwd()
    config_path = root / CONFIG_FILENAME
    if not config_path.exists():
        return ExoPyConfig(persistent_data_dir=root / DEFAULT_PERSISTENT_DATA_DIR)

    values = _read_toml(config_path)
    configured_dir = _persistent_data_dir_value(values)
    dace_rc_config_path = _path_value(values, "dace_rc_config_path", section="dace")
    if configured_dir is None:
        return ExoPyConfig(
            persistent_data_dir=root / DEFAULT_PERSISTENT_DATA_DIR,
            dace_rc_config_path=_resolve_optional_path(dace_rc_config_path, root),
        )

    path = Path(configured_dir).expanduser()
    if not path.is_absolute():
        path = root / path
    return ExoPyConfig(
        persistent_data_dir=path,
        dace_rc_config_path=_resolve_optional_path(dace_rc_config_path, root),
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
        import tomli as tomllib

    with path.open("rb") as handle:
        return tomllib.load(handle)


def _persistent_data_dir_value(values: dict[str, Any]) -> str | None:
    value = _path_value(values, "persistent_data_dir", section="storage")
    return str(value) if value else None


def _path_value(values: dict[str, Any], key: str, section: str) -> str | None:
    value = values.get(key)
    if value:
        return str(value)

    section_values = values.get(section, {})
    if isinstance(section_values, dict) and section_values.get(key):
        return str(section_values[key])
    return None


def _resolve_optional_path(value: str | None, root: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path
