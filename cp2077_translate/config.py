"""Configuration loading from config.toml and CLI overrides."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass
class Config:
    """Runtime configuration for the CP2077 translation pipeline."""

    wolvenkit_cli: Path = Path("WolvenKit.CLI.exe")
    game_dir: Path = Path(".")
    work_dir: Path = Path("./work")
    output_dir: Path = Path("./output")
    mod_name: str = "CP2077Translation"
    mod_version: str = "1.0.0"
    mod_description: str = "Translates CP2077 localization to another language"
    workers: int = 8
    # Translation settings
    provider: str = "anthropic"  # "anthropic" or "openai"
    source_lang: str = "Turkish"
    target_lang: str = "Kazakh"
    source_locale: str = "tr-tr"  # locale dir name in extracted archives
    api_key: str | None = None  # API key (or use ANTHROPIC_API_KEY / OPENAI_API_KEY env var)
    model: str = "claude-sonnet-4-20250514"
    batch_size: int = 40


def load_config(config_path: Path | None = None, **overrides: str) -> Config:
    """Load configuration from a TOML file, with CLI overrides applied on top.

    Relative paths in the config file are resolved relative to the directory
    containing the config file, not the current working directory.
    """
    cfg = Config()

    if config_path and not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    if config_path and config_path.exists():
        base = config_path.resolve().parent

        def _path(raw: str) -> Path:
            p = Path(raw)
            return (base / p).resolve() if not p.is_absolute() else p

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        wk = data.get("wolvenkit", {})
        if "cli_path" in wk:
            cfg.wolvenkit_cli = _path(wk["cli_path"])

        paths = data.get("paths", {})
        if "game_dir" in paths:
            cfg.game_dir = _path(paths["game_dir"])
        if "work_dir" in paths:
            cfg.work_dir = _path(paths["work_dir"])
        if "output_dir" in paths:
            cfg.output_dir = _path(paths["output_dir"])

        mod = data.get("mod", {})
        if "name" in mod:
            cfg.mod_name = mod["name"]
        if "version" in mod:
            cfg.mod_version = mod["version"]
        if "description" in mod:
            cfg.mod_description = mod["description"]

        perf = data.get("performance", {})
        if "workers" in perf:
            cfg.workers = int(perf["workers"])

        translation = data.get("translation", {})
        if "provider" in translation:
            cfg.provider = translation["provider"]
        if "source_lang" in translation:
            cfg.source_lang = translation["source_lang"]
        if "target_lang" in translation:
            cfg.target_lang = translation["target_lang"]
        if "source_locale" in translation:
            cfg.source_locale = translation["source_locale"]
        if "api_key" in translation:
            cfg.api_key = translation["api_key"]
        if "model" in translation:
            cfg.model = translation["model"]
        if "batch_size" in translation:
            cfg.batch_size = int(translation["batch_size"])

    # Apply CLI overrides (resolved relative to CWD)
    if "wolvenkit_path" in overrides and overrides["wolvenkit_path"]:
        cfg.wolvenkit_cli = Path(overrides["wolvenkit_path"])
    if "game_dir" in overrides and overrides["game_dir"]:
        cfg.game_dir = Path(overrides["game_dir"])
    if "work_dir" in overrides and overrides["work_dir"]:
        cfg.work_dir = Path(overrides["work_dir"])
    if "output_dir" in overrides and overrides["output_dir"]:
        cfg.output_dir = Path(overrides["output_dir"])

    # Validate settings
    if cfg.provider not in ("anthropic", "openai"):
        raise ValueError(f"provider must be 'anthropic' or 'openai', got '{cfg.provider}'")
    if cfg.workers < 1 or cfg.workers > 64:
        raise ValueError(f"workers must be 1-64, got {cfg.workers}")
    if cfg.batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {cfg.batch_size}")

    return cfg


def validate_tool_paths(cfg: Config) -> None:
    """Validate that WolvenKit CLI and game directory exist."""
    import shutil

    wk = cfg.wolvenkit_cli
    if not wk.exists() and not shutil.which(str(wk)):
        raise FileNotFoundError(
            f"WolvenKit CLI not found: {wk}\n"
            "Set 'cli_path' in config.toml [wolvenkit] or pass --wolvenkit-path"
        )
    if not cfg.game_dir.exists():
        raise FileNotFoundError(
            f"Game directory not found: {cfg.game_dir}\n"
            "Set 'game_dir' in config.toml [paths] or pass --game-dir"
        )
