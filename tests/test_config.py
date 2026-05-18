from pathlib import Path

from exopy.config import DEFAULT_PERSISTENT_DATA_DIR, load_config


def test_load_config_defaults_to_working_directory_exopy_dir(tmp_path):
    config = load_config(tmp_path)

    assert config.persistent_data_dir == tmp_path / DEFAULT_PERSISTENT_DATA_DIR


def test_load_config_reads_top_level_persistent_data_dir(tmp_path):
    (tmp_path / "exopy_config.toml").write_text(
        'persistent_data_dir = "exo-data"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.persistent_data_dir == tmp_path / "exo-data"


def test_load_config_reads_storage_persistent_data_dir(tmp_path):
    (tmp_path / "exopy_config.toml").write_text(
        '[storage]\npersistent_data_dir = "storage/exopy"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.persistent_data_dir == tmp_path / "storage" / "exopy"


def test_load_config_reads_dace_rc_config_path(tmp_path):
    (tmp_path / "exopy_config.toml").write_text(
        '[dace]\ndace_rc_config_path = "auth/.dacerc"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.dace_rc_config_path == tmp_path / "auth" / ".dacerc"


def test_load_config_reads_top_level_dace_rc_config_path(tmp_path):
    (tmp_path / "exopy_config.toml").write_text(
        'dace_rc_config_path = "auth/.dacerc"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.dace_rc_config_path == tmp_path / "auth" / ".dacerc"


def test_load_config_keeps_absolute_persistent_data_dir(tmp_path):
    absolute = tmp_path / "absolute-exopy"
    (tmp_path / "exopy_config.toml").write_text(
        f'persistent_data_dir = "{absolute}"\n',
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.persistent_data_dir == absolute
