"""CLI entry point for the CP2077 Translation pipeline."""

import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

from .config import load_config, validate_tool_paths
from .extractor import collect_locale_jsons, extract_locale_archives
from .repacker import convert_json_to_cr2w
from .translator import (
    apply_translations,
    extract_strings,
    load_translation_log,
    translate_strings,
    write_translation_log,
    TranslationRecord,
)

logger = logging.getLogger(__name__)


def _setup_logging(output_dir: Path, level: int = logging.INFO) -> str:
    """Configure file logging for pipeline runs. Returns the run ID."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"translation_{run_id}.log"

    root = logging.getLogger("cp2077_translate")
    root.setLevel(level)
    root.propagate = False

    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    logger.info("Translation run %s started", run_id)
    logger.info("Log file: %s", log_path)
    return run_id


app = typer.Typer(
    name="cp2077-translate",
    help="CP2077 Translation Mod - CLI toolchain for translating Cyberpunk 2077 localization files via LLM.",
)


@app.command()
def translate(
    config_file: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config.toml"
    ),
    source_lang: Optional[str] = typer.Option(
        None, "--source-lang", help="Source language name (e.g. 'Turkish')"
    ),
    target_lang: Optional[str] = typer.Option(
        None, "--target-lang", help="Target language name (e.g. 'Kazakh')"
    ),
    source_locale: Optional[str] = typer.Option(
        None, "--source-locale", help="Source locale directory (e.g. 'tr-tr')"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="LLM model to use for translation"
    ),
    batch_size: Optional[int] = typer.Option(
        None, "--batch-size", help="Number of strings per API call"
    ),
    skip_extract: bool = typer.Option(
        False, "--skip-extract", help="Skip extraction (use previously extracted files)"
    ),
    skip_translate: bool = typer.Option(
        False, "--skip-translate", help="Skip translation (apply existing translation log)"
    ),
    skip_repack: bool = typer.Option(
        False, "--skip-repack", help="Skip repacking (translate only, don't build archive)"
    ),
    extract_only: bool = typer.Option(
        False, "--extract-only", help="Only extract strings to CSV, don't translate"
    ),
) -> None:
    """Translate CP2077 localization files from one language to another.

    Extracts text from a source locale archive (default: Turkish), translates
    each string via an LLM API, writes translations back into the JSON files,
    and repacks into a game-ready .archive mod.

    Turkish is recommended as the source for Kazakh translation because both
    are Turkic languages with similar grammar and text length.
    """
    pipeline_start = time.time()

    try:
        config = load_config(config_file)
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    run_id = _setup_logging(config.output_dir)

    # Apply CLI overrides
    src_lang = source_lang or config.source_lang
    tgt_lang = target_lang or config.target_lang
    src_locale = source_locale or config.source_locale
    effective_api_key = api_key or config.api_key or os.environ.get("ANTHROPIC_API_KEY")
    effective_model = model or config.model
    effective_batch_size = batch_size or config.batch_size

    # Derive locale code from locale dir (e.g. "tr-tr" -> "tr")
    locale_code = src_locale.split("-")[0]

    log_path = config.output_dir / "translation_log.csv"

    rprint(f"[bold]Translation pipeline: {src_lang} → {tgt_lang}[/bold]")
    rprint(f"  Source locale: {src_locale} (archive prefix: lang_{locale_code})")
    logger.info("Translation pipeline: %s -> %s, locale=%s, model=%s",
                src_lang, tgt_lang, src_locale, effective_model)

    # Step 1: Extract source locale archives
    if skip_extract:
        rprint("[yellow]Skipping extraction (using existing files)[/yellow]")
        extract_dir = config.work_dir / "extracted"
        if not extract_dir.exists():
            rprint("[red]Error: extracted directory not found. Run without --skip-extract first.[/red]")
            raise typer.Exit(1)
    else:
        try:
            validate_tool_paths(config)
        except FileNotFoundError as e:
            rprint(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        rprint(f"[bold]Step 1: Extracting {src_lang} locale archives...[/bold]")
        extract_dir = extract_locale_archives(config, locale_code, src_locale)

    # Collect locale JSONs
    json_files = collect_locale_jsons(extract_dir, src_locale)
    rprint(f"  Found {len(json_files)} locale file(s)")

    if not json_files:
        rprint(f"[red]No locale files found for '{src_locale}'. "
               f"Check that the game has the {src_lang} language pack installed.[/red]")
        raise typer.Exit(1)

    # Step 2: Extract translatable strings
    rprint("[bold]Step 2: Extracting translatable strings...[/bold]")
    entries = extract_strings(json_files)
    rprint(f"  Extracted {len(entries)} translatable string(s)")

    if extract_only:
        preview_records = [
            TranslationRecord(
                filepath=e.filepath, string_key=e.string_key,
                string_id=e.string_id, field=e.field,
                source_text=e.source_text, translated_text="",
            )
            for e in entries
        ]
        write_translation_log(preview_records, log_path)
        rprint(f"[green]Extracted {len(entries)} strings to {log_path}[/green]")
        raise typer.Exit(0)

    # Step 3: Translate
    if skip_translate:
        rprint("[yellow]Skipping translation (using existing log)[/yellow]")
        try:
            records = load_translation_log(log_path)
        except FileNotFoundError:
            rprint(f"[red]Error: translation log not found at {log_path}[/red]")
            raise typer.Exit(1)
        rprint(f"  Loaded {len(records)} translation(s) from log")
    else:
        if not effective_api_key:
            rprint("[red]Error: No API key provided. Set ANTHROPIC_API_KEY env var, "
                   "pass --api-key, or set api_key in config.toml [translation].[/red]")
            raise typer.Exit(1)

        rprint(f"[bold]Step 3: Translating {len(entries)} strings ({src_lang} → {tgt_lang})...[/bold]")
        records = translate_strings(
            entries, src_lang, tgt_lang,
            effective_api_key, effective_model, effective_batch_size,
            resume_log=log_path,
        )
        write_translation_log(records, log_path)
        rprint(f"  Translation log saved to {log_path}")

    # Step 4: Apply translations to JSON files
    rprint("[bold]Step 4: Applying translations to locale files...[/bold]")
    updated = apply_translations(json_files, records)
    rprint(f"  Updated {updated} string(s) in locale files")

    if skip_repack:
        rprint("[yellow]Skipping repack.[/yellow]")
        elapsed = time.time() - pipeline_start
        rprint(f"[green bold]Translation complete ({elapsed:.1f}s)[/green bold]")
        raise typer.Exit(0)

    # Step 5: Repack
    try:
        validate_tool_paths(config)
    except FileNotFoundError as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint("[bold]Step 5: Repacking translated archive...[/bold]")

    # Convert all translated .json.json files back to CR2W
    modified_files = {Path(r.filepath).resolve() for r in records}
    convert_json_to_cr2w(config, extract_dir, modified_files)

    # Pack into archive
    cmd = [str(config.wolvenkit_cli), "pack", "-p", str(extract_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        rprint(f"[red]WolvenKit pack failed (exit {result.returncode})[/red]")
        if result.stderr:
            rprint(f"[dim]{result.stderr.strip()}[/dim]")
        raise typer.Exit(1)

    packed_dir = extract_dir.parent
    archives = list(packed_dir.glob("*.archive"))
    rprint(f"  Repacked {len(archives)} archive(s)")

    elapsed = time.time() - pipeline_start
    rprint(f"[green bold]Done! Translation pipeline complete ({elapsed:.1f}s)[/green bold]")
    rprint(f"  Install the .archive file(s) from {packed_dir} into your game's archive/pc/mod/ directory.")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
