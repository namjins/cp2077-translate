"""Tests for config.py: validation and path resolution."""

import pytest
from pathlib import Path

from cp2077_translate.config import Config, load_config


class TestConfigValidation:
    def test_workers_range_validated_on_load(self, tmp_path):
        """Workers validation is tested via test_workers_zero_raises and test_workers_too_high_raises."""
        cfg = Config()
        assert 1 <= cfg.workers <= 64

    def test_default_config(self):
        """Default Config() should have sane defaults."""
        cfg = Config()
        assert cfg.workers == 8
        assert cfg.batch_size == 40
        assert cfg.source_lang == "Turkish"
        assert cfg.target_lang == "Kazakh"
        assert cfg.source_locale == "tr-tr"

    def test_config_from_toml(self, tmp_path):
        """Config loads correctly from a TOML file."""
        toml_content = """
[performance]
workers = 4

[translation]
source_lang = "Russian"
target_lang = "Kazakh"
source_locale = "ru-ru"
batch_size = 20
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(toml_content)

        cfg = load_config(config_file)
        assert cfg.workers == 4
        assert cfg.source_lang == "Russian"
        assert cfg.source_locale == "ru-ru"
        assert cfg.batch_size == 20

    def test_workers_zero_raises(self, tmp_path):
        toml = "[performance]\nworkers = 0\n"
        config_file = tmp_path / "config.toml"
        config_file.write_text(toml)
        with pytest.raises(ValueError, match="workers"):
            load_config(config_file)

    def test_workers_too_high_raises(self, tmp_path):
        toml = "[performance]\nworkers = 100\n"
        config_file = tmp_path / "config.toml"
        config_file.write_text(toml)
        with pytest.raises(ValueError, match="workers"):
            load_config(config_file)

    def test_missing_config_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config(Path("nonexistent.toml"))

    def test_relative_paths_resolved_from_config_dir(self, tmp_path):
        """Relative paths in TOML should resolve relative to config file location."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        toml = '[paths]\nwork_dir = "../work"\n'
        (sub / "config.toml").write_text(toml)

        cfg = load_config(sub / "config.toml")
        assert cfg.work_dir == (tmp_path / "work").resolve()
