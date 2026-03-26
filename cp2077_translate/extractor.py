"""Extract localization JSON files from Cyberpunk 2077 archives using WolvenKit CLI."""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from .config import Config

logger = logging.getLogger(__name__)


def find_locale_archives(game_dir: Path, locale_code: str = "en") -> list[Path]:
    """Find .archive files that contain localization data for a given locale.

    Searches both base game (archive/pc/content/) and Phantom Liberty
    expansion (archive/pc/ep1/) directories.

    Args:
        game_dir: Path to the Cyberpunk 2077 installation.
        locale_code: Two-letter locale prefix (e.g. "en", "tr", "ru").
    """
    search_dirs = [
        ("base game", game_dir / "archive" / "pc" / "content"),
        ("Phantom Liberty", game_dir / "archive" / "pc" / "ep1"),
    ]

    primary_name = f"lang_{locale_code}_text.archive"

    archives: list[Path] = []
    for label, archive_dir in search_dirs:
        if not archive_dir.exists():
            continue

        found = list(archive_dir.glob(primary_name))
        if not found:
            # Fallback: any text archive with the locale prefix (exclude voice)
            found = [
                p for p in archive_dir.glob(f"*lang_{locale_code}*.archive")
                if "voice" not in p.name.lower()
            ]

        if found:
            print(f"  Found {len(found)} locale archive(s) in {label}: {archive_dir}")
            archives.extend(found)

    if not archives:
        raise FileNotFoundError(
            f"No '{locale_code}' locale archive found in {game_dir / 'archive' / 'pc'}. "
            f"Expected '{primary_name}' in content/ and/or ep1/. "
            "Check that game_dir points to your Cyberpunk 2077 installation."
        )

    return sorted(archives)


def convert_cr2w_to_json(config: Config, extract_dir: Path, locale: str = "en-us") -> list[Path]:
    """Convert CR2W locale files to plain JSON using WolvenKit cr2w -s.

    WolvenKit unbundle produces CR2W binary files with a .json extension.
    Running 'cr2w -s' on each file produces a .json.json file containing
    the actual human-readable JSON that can be scanned and patched.

    Returns the list of .json.json files produced.
    """
    cr2w_files = [
        p for p in extract_dir.rglob("*.json")
        if not p.name.endswith(".json.json")
        and _is_locale_path(p, locale)
    ]

    if not cr2w_files:
        print("  Warning: no CR2W locale files found to convert.")
        return []

    def _convert_one(cr2w_file: Path) -> Path | None:
        expected_output = cr2w_file.parent / (cr2w_file.name + ".json")
        cmd = [str(config.wolvenkit_cli), "cr2w", "-s", str(cr2w_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("cr2w conversion failed for %s (exit %d): %s",
                           cr2w_file.name, result.returncode, (result.stderr or "").strip()[:500])
            print(f"  Warning: cr2w conversion failed for {cr2w_file.name}")
            if result.stderr:
                print(f"  stderr: {result.stderr.strip()}")
            return None
        return expected_output if expected_output.exists() else None

    produced: list[Path] = []
    failed_count = 0
    with Progress(
        TextColumn("  [bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(
            f"Converting CR2W ({config.workers} workers)", total=len(cr2w_files)
        )
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures = {executor.submit(_convert_one, f): f for f in cr2w_files}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    produced.append(result)
                else:
                    failed_count += 1
                progress.advance(task)

    if failed_count:
        total = len(cr2w_files)
        pct = (failed_count / total) * 100 if total else 0
        print(f"  Warning: {failed_count}/{total} CR2W conversion(s) failed ({pct:.1f}%)")
        if pct > 10:
            raise RuntimeError(
                f"CR2W conversion failure rate too high: {failed_count}/{total} ({pct:.1f}%). "
                "Check WolvenKit installation and game files."
            )

    return sorted(produced)


def extract_locale_archives(config: Config, locale_code: str, locale_dir: str) -> Path:
    """Extract archives for a specific locale (e.g. Turkish).

    Similar to extract_archives but targets a specific locale code and directory.

    Args:
        config: Pipeline configuration.
        locale_code: Two-letter code for archive lookup (e.g. "tr").
        locale_dir: Locale directory name in extracted paths (e.g. "tr-tr").

    Returns the path to the extraction output directory.
    """
    extract_dir = config.work_dir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    archives = find_locale_archives(config.game_dir, locale_code)
    for archive in archives:
        print(f"  Unbundling: {archive.name}")
        cmd = [
            str(config.wolvenkit_cli),
            "unbundle",
            "-p", str(archive),
            "-o", str(extract_dir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("WolvenKit unbundle failed for %s (exit %d): %s",
                           archive.name, result.returncode, (result.stderr or "").strip()[:500])

    produced = convert_cr2w_to_json(config, extract_dir, locale_dir)
    print(f"  CR2W conversion produced {len(produced)} .json.json file(s)")
    if not produced:
        print("  Warning: no JSON files were produced -- check WolvenKit output above")

    return extract_dir


def _is_locale_path(path: Path, locale: str) -> bool:
    """Return True if the path is under a locale directory.

    Matches both hyphenated (en-us) and underscored (en_us) variants
    case-insensitively.
    """
    parts_lower = [p.lower() for p in path.parts]
    hyphenated = locale.lower()
    underscored = hyphenated.replace("-", "_")
    return hyphenated in parts_lower or underscored in parts_lower


def collect_locale_jsons(extract_dir: Path, locale: str) -> list[Path]:
    """Collect all converted locale JSON files (.json.json).

    These are the plain-JSON outputs produced by 'cr2w -s'.
    Only includes files under the given locale path (e.g. "tr-tr").
    """
    json_files = [
        p for p in extract_dir.rglob("*.json.json")
        if _is_locale_path(p, locale)
    ]
    return sorted(json_files)


def extract_entries(data: object) -> list:
    """Extract locale entries from a WolvenKit cr2w -s JSON export.

    WolvenKit wraps CR2W content in:
      { "Header": {...}, "Data": { "RootChunk": { "root": { "Data": { "entries": [...] } } } } }

    Falls back to a direct "entries" key or plain list for simpler structures.
    """
    if isinstance(data, dict):
        # WolvenKit cr2w -s wrapper path
        try:
            entries = data["Data"]["RootChunk"]["root"]["Data"]["entries"]
            if isinstance(entries, list):
                return entries
        except (KeyError, TypeError):
            pass

        # Fallback: flat dict with entries key
        if "entries" in data:
            entries = data["entries"]
            if isinstance(entries, list):
                return entries

    if isinstance(data, list):
        return data

    return []
