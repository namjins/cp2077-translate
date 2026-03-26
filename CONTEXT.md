# Translation Pipeline Context Reference

## Pipeline Overview

This tool translates Cyberpunk 2077's in-game text (subtitles, UI, dialogue) from one language to another using an LLM API. It reuses CP2077's existing localization infrastructure — extracting text from game archives, translating via API, and repacking into a game-ready mod.

### Why translate from Turkish (not English)?

Kazakh and Turkish are both Turkic languages. Translating Turkish → Kazakh produces much better results than English → Kazakh because:
- Near-identical grammar (agglutinative, SOV, vowel harmony, no grammatical gender)
- Similar vocabulary and word formation
- Comparable text length — if Turkish fits the game's UI, Kazakh will too

---

## Stage I/O Contracts

| Stage | Input | Output | Module |
|-------|-------|--------|--------|
| 1. Extract | `lang_<xx>_text.archive` (base + EP1) | `work/extracted/**/*.json.json` | `extractor.py` |
| 2. Extract strings | `.json.json` files | `TranslationEntry` list | `translator.py` |
| 3. Translate | `TranslationEntry` list + API key | `TranslationRecord` list + `translation_log.csv` | `translator.py` |
| 4. Apply | `TranslationRecord` list + `.json.json` files | modified `.json.json` files | `translator.py` |
| 5. Repack | modified `.json.json` files | `work/*.archive` | `repacker.py` |

The pipeline is sequential. The `--skip-*` flags allow re-entering at any stage.

---

## Data Formats

### Locale JSON entry (after CR2W conversion)

```json
{
  "secondaryKey": "judy_romance_03",
  "stringId": 12345,
  "femaleVariant": "Dialogue text (female V)",
  "maleVariant": "Dialogue text (male V)"
}
```

### translation_log.csv

Written incrementally during translation for resume support.

Columns: `filepath,string_key,string_id,field,source_text,translated_text`

---

## Module Dependency Map

```
config.py          ← loaded at startup
fileutil.py        ← atomic_write() used by translator.py, packager.py
extractor.py       ← WolvenKit extraction + CR2W conversion + entry parsing
translator.py      ← string extraction, LLM batching, application
repacker.py        ← CR2W deserialization + WolvenKit pack
packager.py        ← zip packaging

Data flow:
  extractor.py → work/extracted/ → translator.py → repacker.py → *.archive
```
