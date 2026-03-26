"""Translate CP2077 localization strings using an LLM API."""

import csv
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from .fileutil import atomic_write
from .extractor import extract_entries

logger = logging.getLogger(__name__)

# Variant fields that contain translatable dialogue text.
VARIANT_FIELDS = ("femaleVariant", "maleVariant")

# Default batch size: number of strings sent per API call.
DEFAULT_BATCH_SIZE = 40


@dataclass
class TranslationEntry:
    """A single string extracted from a locale file for translation."""

    filepath: str
    string_key: str
    string_id: str | None
    field: str
    source_text: str


@dataclass
class TranslationRecord:
    """A completed translation mapping source to target text."""

    filepath: str
    string_key: str
    string_id: str | None
    field: str
    source_text: str
    translated_text: str


def extract_strings(json_files: list[Path]) -> list[TranslationEntry]:
    """Extract all translatable strings from locale JSON files.

    Walks the WolvenKit cr2w -s JSON structure and pulls out every non-empty
    femaleVariant/maleVariant string along with its identifying metadata.
    """
    entries: list[TranslationEntry] = []
    skipped_files = 0

    with Progress(
        TextColumn("  [bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Extracting strings", total=len(json_files))

        for filepath in json_files:
            try:
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("Skipping %s: %s", filepath.name, e)
                skipped_files += 1
                progress.advance(task)
                continue

            for entry in extract_entries(data):
                if not isinstance(entry, dict):
                    continue

                entry_key = entry.get("secondaryKey", entry.get("$type", "unknown"))
                string_id = entry.get("stringId")

                for field_name in VARIANT_FIELDS:
                    value = entry.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        continue

                    entries.append(TranslationEntry(
                        filepath=str(filepath),
                        string_key=str(entry_key),
                        string_id=str(string_id) if string_id is not None else None,
                        field=field_name,
                        source_text=value,
                    ))

            progress.advance(task)

    logger.info("String extraction: %d entries from %d file(s) (%d file(s) skipped)",
                len(entries), len(json_files) - skipped_files, skipped_files)
    return entries


def _build_translation_prompt(
    batch: list[TranslationEntry],
    source_lang: str,
    target_lang: str,
) -> str:
    """Build the translation prompt for a batch of strings.

    The prompt instructs the LLM to return a JSON array of translated strings,
    preserving inline markup tags and {variable} placeholders.
    """
    lines = [
        f"Translate the following {source_lang} dialogue strings from Cyberpunk 2077 into {target_lang}.",
        "",
        "Rules:",
        "- Preserve all HTML/XML tags (e.g. <color>, </i>) exactly as they appear.",
        "- Preserve all {variable} placeholders (e.g. {player_name}) exactly as they appear.",
        "- Maintain the tone, register, and character voice of each line.",
        "- The secondaryKey gives context about who is speaking and the scene.",
        "- Return ONLY a JSON array of translated strings, one per input, in the same order.",
        "- Do NOT include any explanation, markdown formatting, or code fences.",
        "",
        "Input strings:",
        "",
    ]

    for i, entry in enumerate(batch):
        lines.append(f'[{i}] (key: {entry.string_key}, field: {entry.field})')
        lines.append(f'    {json.dumps(entry.source_text, ensure_ascii=False)}')
        lines.append("")

    lines.append(f"Return a JSON array of exactly {len(batch)} translated strings.")

    return "\n".join(lines)


def _parse_translation_response(response_text: str, expected_count: int) -> list[str]:
    """Parse the LLM response into a list of translated strings.

    Expects a JSON array of strings. Strips any markdown code fences the LLM
    may have added despite instructions.
    """
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (possibly with language tag)
        first_newline = text.find("\n")
        if first_newline == -1:
            text = text[3:]  # No newline — strip the opening ``` only
        else:
            text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    # Try direct parse first; fall back to extracting the JSON array from surrounding text
    try:
        translations = json.loads(text)
    except json.JSONDecodeError:
        # Find the opening bracket and try closing brackets from the array end inward,
        # in case the LLM added trailing text containing brackets (e.g. "[tags]").
        start = text.find("[")
        if start == -1:
            raise
        end = text.rfind("]")
        while end > start:
            try:
                translations = json.loads(text[start:end + 1])
                break
            except json.JSONDecodeError:
                end = text.rfind("]", start, end)
        else:
            # No valid JSON array found — re-raise the original error
            translations = json.loads(text)

    if not isinstance(translations, list):
        raise ValueError(f"Expected JSON array, got {type(translations).__name__}")

    if len(translations) != expected_count:
        raise ValueError(
            f"Expected {expected_count} translations, got {len(translations)}"
        )

    # Validate each element is a scalar (string, number, bool), not a dict/list
    result: list[str] = []
    for i, t in enumerate(translations):
        if isinstance(t, (dict, list)):
            raise ValueError(
                f"Translation [{i}] is {type(t).__name__}, expected string"
            )
        result.append(str(t))

    return result


def translate_batch_anthropic(
    batch: list[TranslationEntry],
    source_lang: str,
    target_lang: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    client: object | None = None,
) -> list[str]:
    """Translate a batch of strings using the Anthropic Messages API.

    Uses the anthropic SDK if available, otherwise falls back to direct HTTP.
    An optional pre-built ``client`` avoids re-creating connections per batch.
    """
    prompt = _build_translation_prompt(batch, source_lang, target_lang)

    try:
        import anthropic
        if client is None:
            client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "max_tokens":
            raise ValueError(
                "Response truncated (hit max_tokens). "
                "Try reducing batch_size in config.toml."
            )
        response_text = response.content[0].text
    except ImportError:
        import urllib.request
        import urllib.error

        request_body = json.dumps({
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Anthropic API error {e.code}: {body}"
            ) from e

        if resp_data.get("stop_reason") == "max_tokens":
            raise ValueError(
                "Response truncated (hit max_tokens). "
                "Try reducing batch_size in config.toml."
            )
        response_text = resp_data["content"][0]["text"]

    return _parse_translation_response(response_text, len(batch))


def translate_strings(
    entries: list[TranslationEntry],
    source_lang: str,
    target_lang: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume_log: Path | None = None,
) -> list[TranslationRecord]:
    """Translate all extracted strings in batches via an LLM API.

    If resume_log points to an existing translation log, already-translated
    entries are skipped to allow resuming interrupted runs.

    Returns a list of TranslationRecords for all translated strings.
    """
    # Load already-translated keys from resume log
    done_keys: set[tuple[str, str, str | None, str]] = set()
    existing_records: list[TranslationRecord] = []
    if resume_log and resume_log.exists():
        existing_records = load_translation_log(resume_log)
        for r in existing_records:
            done_keys.add((r.filepath, r.string_key, r.string_id, r.field))
        logger.info("Resuming: %d entries already translated", len(done_keys))

    remaining = [
        e for e in entries
        if (e.filepath, e.string_key, e.string_id, e.field) not in done_keys
    ]

    if not remaining:
        logger.info("All %d strings already translated (nothing to do)", len(done_keys))
        print("  All strings already translated (nothing to do).")
        return existing_records

    logger.info("Translation plan: %d remaining, %d already done, batch_size=%d",
                len(remaining), len(done_keys), batch_size)
    print(f"  {len(remaining)} string(s) to translate ({len(done_keys)} already done)")

    records = list(existing_records)

    # Build a reusable API client if the SDK is available
    api_client = None
    try:
        import anthropic
        api_client = anthropic.Anthropic(api_key=api_key)
        logger.debug("Using anthropic SDK for API calls")
    except ImportError:
        logger.debug("anthropic SDK not available, using urllib fallback")

    # Process in batches
    max_retries = 3
    batches = [remaining[i:i + batch_size] for i in range(0, len(remaining), batch_size)]

    with Progress(
        TextColumn("  [bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(
            f"Translating ({len(batches)} batches)", total=len(batches)
        )

        for batch_idx, batch in enumerate(batches):
            translations = None
            for attempt in range(1, max_retries + 1):
                try:
                    translations = translate_batch_anthropic(
                        batch, source_lang, target_lang, api_key, model,
                        client=api_client,
                    )
                    break
                except Exception as e:
                    logger.warning("Batch attempt %d/%d failed: %s", attempt, max_retries, e)
                    if attempt == max_retries:
                        logger.error("Batch translation failed after %d attempts: %s", max_retries, e)
                        print(f"\n  Error translating batch after {max_retries} attempts: {e}")
                        print("  Saving progress so far. Re-run to resume.")
                    else:
                        wait = 2 ** attempt
                        print(f"\n  Retry {attempt}/{max_retries} in {wait}s...")
                        time.sleep(wait)

            if translations is None:
                break

            logger.debug("Batch %d/%d complete: %d string(s) translated",
                         batch_idx + 1, len(batches), len(translations))

            for entry, translated in zip(batch, translations):
                records.append(TranslationRecord(
                    filepath=entry.filepath,
                    string_key=entry.string_key,
                    string_id=entry.string_id,
                    field=entry.field,
                    source_text=entry.source_text,
                    translated_text=translated,
                ))

            # Write incremental progress after each batch
            if resume_log:
                write_translation_log(records, resume_log)

            progress.advance(task)

    new_count = len(records) - len(existing_records)
    logger.info("Translation done: %d new record(s), %d total", new_count, len(records))
    return records


def apply_translations(
    json_files: list[Path],
    records: list[TranslationRecord],
) -> int:
    """Write translated strings back into the locale JSON files.

    Modifies the JSON files in-place, replacing source text with translations.
    Returns the number of entries updated.
    """
    # Index records by (filepath, string_key, string_id, field) for fast lookup
    lookup: dict[tuple[str, str, str | None, str], str] = {}
    for r in records:
        lookup[(r.filepath, r.string_key, r.string_id, r.field)] = r.translated_text

    logger.info("Applying translations: %d record(s) to %d file(s)", len(lookup), len(json_files))

    updated_count = 0
    modified_file_count = 0

    with Progress(
        TextColumn("  [bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Applying translations", total=len(json_files))

        for filepath in json_files:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            entries = extract_entries(data)
            modified = False

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                entry_key = str(entry.get("secondaryKey", entry.get("$type", "unknown")))
                string_id = entry.get("stringId")
                sid = str(string_id) if string_id is not None else None
                fp_str = str(filepath)

                for field_name in VARIANT_FIELDS:
                    value = entry.get(field_name)
                    if not isinstance(value, str) or not value.strip():
                        continue

                    key = (fp_str, entry_key, sid, field_name)
                    if key in lookup:
                        entry[field_name] = lookup[key]
                        modified = True
                        updated_count += 1

            if modified:
                serialized = json.dumps(data, ensure_ascii=False, indent=2)
                json.loads(serialized)  # sanity check round-trip
                with atomic_write(filepath, encoding="utf-8") as f:
                    f.write(serialized)
                modified_file_count += 1

            progress.advance(task)

    logger.info("Apply complete: %d string(s) updated across %d file(s)",
                updated_count, modified_file_count)
    return updated_count


def write_translation_log(records: list[TranslationRecord], output_path: Path) -> None:
    """Write translation records to a CSV log for auditing and resume support."""
    with atomic_write(output_path, newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "filepath", "string_key", "string_id", "field",
            "source_text", "translated_text",
        ])
        for rec in records:
            writer.writerow([
                rec.filepath, rec.string_key, rec.string_id or "",
                rec.field, rec.source_text, rec.translated_text,
            ])


def load_translation_log(log_path: Path) -> list[TranslationRecord]:
    """Load translation records from an existing CSV log.

    Used to resume interrupted translation runs.
    """
    if not log_path.exists():
        raise FileNotFoundError(f"Translation log not found: {log_path}")

    required_columns = {"filepath", "string_key", "string_id", "field",
                        "source_text", "translated_text"}

    records: list[TranslationRecord] = []
    with open(log_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"Translation log is empty: {log_path}")
        missing = required_columns - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Translation log missing columns: {missing}")

        for row in reader:
            records.append(TranslationRecord(
                filepath=row["filepath"],
                string_key=row["string_key"],
                string_id=row["string_id"] or None,
                field=row["field"],
                source_text=row["source_text"],
                translated_text=row["translated_text"],
            ))

    return records
