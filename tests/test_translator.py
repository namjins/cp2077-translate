"""Tests for translator.py: string extraction, prompt building, response parsing, and log I/O."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from cp2077_translate.translator import (
    TranslationEntry,
    TranslationRecord,
    extract_strings,
    apply_translations,
    write_translation_log,
    load_translation_log,
    _build_translation_prompt,
    _parse_translation_response,
)


def _make_locale_json(entries):
    """Build a WolvenKit cr2w -s style JSON structure."""
    return {
        "Data": {"RootChunk": {"root": {"Data": {"entries": entries}}}}
    }


# -- extract_strings --------------------------------------------------------

class TestExtractStrings:
    def test_extracts_both_variants(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "judy_scene_01",
                "stringId": 100,
                "femaleVariant": "Hello there",
                "maleVariant": "Hey there",
            }
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        entries = extract_strings([filepath])
        assert len(entries) == 2
        assert entries[0].field == "femaleVariant"
        assert entries[0].source_text == "Hello there"
        assert entries[1].field == "maleVariant"
        assert entries[1].source_text == "Hey there"

    def test_skips_empty_strings(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "empty_line",
                "stringId": 200,
                "femaleVariant": "",
                "maleVariant": "   ",
            }
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        entries = extract_strings([filepath])
        assert len(entries) == 0

    def test_skips_non_string_variants(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "weird",
                "stringId": 300,
                "femaleVariant": 12345,
                "maleVariant": None,
            }
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        entries = extract_strings([filepath])
        assert len(entries) == 0

    def test_preserves_string_id(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "key1",
                "stringId": 42,
                "femaleVariant": "text",
                "maleVariant": "",
            }
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        entries = extract_strings([filepath])
        assert entries[0].string_id == "42"

    def test_handles_missing_string_id(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "no_id",
                "femaleVariant": "text",
                "maleVariant": "",
            }
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        entries = extract_strings([filepath])
        assert entries[0].string_id is None

    def test_skips_malformed_json(self, tmp_path):
        filepath = tmp_path / "bad.json.json"
        filepath.write_text("not json {{{", encoding="utf-8")

        entries = extract_strings([filepath])
        assert entries == []

    def test_multiple_files(self, tmp_path):
        for i in range(3):
            data = _make_locale_json([
                {
                    "secondaryKey": f"key_{i}",
                    "stringId": i,
                    "femaleVariant": f"Line {i}",
                    "maleVariant": "",
                }
            ])
            (tmp_path / f"file{i}.json.json").write_text(
                json.dumps(data), encoding="utf-8"
            )

        files = sorted(tmp_path.glob("*.json.json"))
        entries = extract_strings(files)
        assert len(entries) == 3


# -- _build_translation_prompt ---------------------------------------------

class TestBuildPrompt:
    def test_includes_source_and_target_lang(self):
        entries = [
            TranslationEntry("f.json", "key1", "1", "femaleVariant", "Merhaba"),
        ]
        prompt = _build_translation_prompt(entries, "Turkish", "Kazakh")
        assert "Turkish" in prompt
        assert "Kazakh" in prompt

    def test_includes_string_key_for_context(self):
        entries = [
            TranslationEntry("f.json", "judy_romance_03", "1", "femaleVariant", "text"),
        ]
        prompt = _build_translation_prompt(entries, "Turkish", "Kazakh")
        assert "judy_romance_03" in prompt

    def test_includes_all_entries(self):
        entries = [
            TranslationEntry("f.json", f"key{i}", str(i), "femaleVariant", f"text{i}")
            for i in range(5)
        ]
        prompt = _build_translation_prompt(entries, "Turkish", "Kazakh")
        for i in range(5):
            assert f"text{i}" in prompt

    def test_requests_correct_count(self):
        entries = [
            TranslationEntry("f.json", "k", "1", "femaleVariant", "hello"),
            TranslationEntry("f.json", "k2", "2", "maleVariant", "world"),
        ]
        prompt = _build_translation_prompt(entries, "English", "Kazakh")
        assert "exactly 2" in prompt


# -- _parse_translation_response -------------------------------------------

class TestParseResponse:
    def test_parses_clean_json_array(self):
        response = '["Translated one", "Translated two"]'
        result = _parse_translation_response(response, 2)
        assert result == ["Translated one", "Translated two"]

    def test_strips_markdown_code_fences(self):
        response = '```json\n["One", "Two"]\n```'
        result = _parse_translation_response(response, 2)
        assert result == ["One", "Two"]

    def test_raises_on_wrong_count(self):
        response = '["One"]'
        with pytest.raises(ValueError, match="Expected 3"):
            _parse_translation_response(response, 3)

    def test_raises_on_non_array(self):
        response = '{"key": "value"}'
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_translation_response(response, 1)

    def test_raises_on_invalid_json(self):
        response = "not json at all"
        with pytest.raises(json.JSONDecodeError):
            _parse_translation_response(response, 1)

    def test_converts_non_strings_to_string(self):
        response = '[123, true, "text"]'
        result = _parse_translation_response(response, 3)
        assert result == ["123", "True", "text"]


# -- apply_translations ----------------------------------------------------

class TestApplyTranslations:
    def test_applies_translations_to_file(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "test_key",
                "stringId": 1,
                "femaleVariant": "Hello",
                "maleVariant": "Hi",
            }
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        records = [
            TranslationRecord(
                filepath=str(filepath),
                string_key="test_key",
                string_id="1",
                field="femaleVariant",
                source_text="Hello",
                translated_text="Translated Hello",
            ),
        ]

        count = apply_translations([filepath], records)
        assert count == 1

        result = json.loads(filepath.read_text(encoding="utf-8"))
        entry = result["Data"]["RootChunk"]["root"]["Data"]["entries"][0]
        assert entry["femaleVariant"] == "Translated Hello"
        assert entry["maleVariant"] == "Hi"  # unchanged

    def test_no_match_no_modification(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "other_key",
                "stringId": 2,
                "femaleVariant": "Original",
                "maleVariant": "",
            }
        ])
        filepath = tmp_path / "test.json.json"
        original_text = json.dumps(data)
        filepath.write_text(original_text, encoding="utf-8")

        records = [
            TranslationRecord(
                filepath=str(filepath),
                string_key="nonexistent_key",
                string_id="999",
                field="femaleVariant",
                source_text="Nope",
                translated_text="Still nope",
            ),
        ]

        count = apply_translations([filepath], records)
        assert count == 0

    def test_applies_multiple_translations(self, tmp_path):
        data = _make_locale_json([
            {
                "secondaryKey": "key1",
                "stringId": 1,
                "femaleVariant": "Line A",
                "maleVariant": "Line B",
            },
            {
                "secondaryKey": "key2",
                "stringId": 2,
                "femaleVariant": "Line C",
                "maleVariant": "",
            },
        ])
        filepath = tmp_path / "test.json.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        records = [
            TranslationRecord(str(filepath), "key1", "1", "femaleVariant", "Line A", "Translated A"),
            TranslationRecord(str(filepath), "key1", "1", "maleVariant", "Line B", "Translated B"),
            TranslationRecord(str(filepath), "key2", "2", "femaleVariant", "Line C", "Translated C"),
        ]

        count = apply_translations([filepath], records)
        assert count == 3


# -- translation log I/O ---------------------------------------------------

class TestTranslationLog:
    def test_round_trip(self, tmp_path):
        records = [
            TranslationRecord(
                filepath="test.json.json",
                string_key="key1",
                string_id="123",
                field="femaleVariant",
                source_text="Merhaba",
                translated_text="Salam",
            ),
            TranslationRecord(
                filepath="test2.json.json",
                string_key="key2",
                string_id=None,
                field="maleVariant",
                source_text="Goodbye",
                translated_text="Qosh",
            ),
        ]
        log_path = tmp_path / "translation_log.csv"
        write_translation_log(records, log_path)
        loaded = load_translation_log(log_path)

        assert len(loaded) == 2
        assert loaded[0].string_id == "123"
        assert loaded[0].source_text == "Merhaba"
        assert loaded[0].translated_text == "Salam"
        assert loaded[1].string_id is None

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_translation_log(tmp_path / "nonexistent.csv")

    def test_load_empty_file_raises(self, tmp_path):
        log_path = tmp_path / "empty.csv"
        log_path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            load_translation_log(log_path)

    def test_load_missing_columns_raises(self, tmp_path):
        log_path = tmp_path / "bad.csv"
        log_path.write_text("filepath,string_key\nfoo,bar\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing columns"):
            load_translation_log(log_path)
