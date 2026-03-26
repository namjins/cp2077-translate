# CP2077 Translation Pipeline

CLI toolchain that extracts localization text from Cyberpunk 2077 game archives, translates it to another language using an LLM API (Anthropic Claude or OpenAI GPT), and repacks the result as an installable mod.

## What This Does

- **Extracts** all translatable strings (subtitles, dialogue, UI text) from any supported source locale
- **Translates** via Anthropic or OpenAI API in batches, preserving character tone, markup tags, and variable placeholders
- **Repacks** translated text into a game-ready `.archive` mod you can drop into your game
- Covers both the **base game** and **Phantom Liberty** expansion
- **Resumable** -- interrupted translation runs pick up where they left off without re-translating completed batches
- **Any language pair** -- configure source and target languages via config file or command-line flags

> **Disclaimer:** This tool uses AI-generated translation -- mistakes, awkward phrasing, and outright errors will occur. It is not a substitute for professional localization. Additionally, this tool calls paid API services using your own API key. A full game translation can cost anywhere from ~$4 to $400+ depending on the model. You are solely responsible for any API charges you incur. See [Disclaimers](#disclaimers) for details.

## Prerequisites

| Tool | Purpose | Where to get |
|------|---------|--------------|
| **Python 3.11+** | Runs the pipeline | [python.org](https://www.python.org/downloads/) |
| **WolvenKit CLI** | Extracts and repacks CP2077 `.archive` files | [GitHub Releases](https://github.com/WolvenKit/WolvenKit/releases) |
| **API key** (Anthropic or OpenAI) | Powers the LLM translation | [console.anthropic.com](https://console.anthropic.com/) or [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Cyberpunk 2077** | Must have the source language pack installed | Steam/GOG/Epic game settings |

> **Windows required.** WolvenKit CLI is Windows-only, so the pipeline must run on Windows.

## Installation

### 1. Clone and install

```powershell
git clone <repo-url>
cd cp2077-translate
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[anthropic]"
# Or, for OpenAI:
pip install -e ".[openai]"
```

> **"Scripts cannot be loaded" error?** Run this once first:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

> **Provider SDKs are optional.** If you omit `[anthropic]` or `[openai]` from the install (`pip install -e .`), the pipeline falls back to raw HTTP requests automatically. The SDK is recommended because it reuses connections across batches.

### 2. Configure

Copy the example config and edit it:

```powershell
copy config.toml.example config.toml
notepad config.toml
```

At minimum, you need to set:

- **`cli_path`** -- full path to your `WolvenKit.CLI.exe`
- **`game_dir`** -- full path to your Cyberpunk 2077 installation folder
- **`source_lang` / `target_lang`** -- the language pair you want (see [Choosing Languages](#choosing-languages))
- **`source_locale`** -- the locale directory name matching your source language

### 3. Set your API key

Pick one method:

```powershell
# Option A: environment variable (recommended -- keeps keys out of files)
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # for Anthropic
$env:OPENAI_API_KEY = "sk-..."          # for OpenAI

# Option B: in config.toml under [translation]
api_key = "sk-ant-..."

# Option C: command-line flag
cp2077-translate --config config.toml --api-key "sk-ant-..."
```

The pipeline auto-detects the correct env var based on your `provider` setting.

## Choosing Languages

The pipeline works with **any language pair** that Cyberpunk 2077 supports as a source and that the LLM can translate to. You control this with three settings:

| Setting | What it does | Example values |
|---------|-------------|----------------|
| `source_lang` | Human-readable source language name (used in the LLM prompt) | `"Turkish"`, `"English"`, `"Russian"`, `"Japanese"` |
| `target_lang` | Human-readable target language name (used in the LLM prompt) | `"Kazakh"`, `"French"`, `"Ukrainian"`, `"Korean"` |
| `source_locale` | Locale directory name in the game's extracted archives | `"tr-tr"`, `"en-us"`, `"ru-ru"`, `"ja-jp"` |

### Setting languages in config.toml

```toml
[translation]
source_lang = "English"
target_lang = "French"
source_locale = "en-us"
```

### Setting languages on the command line

Command-line flags override whatever is in `config.toml`:

```powershell
cp2077-translate --config config.toml \
    --source-lang English --target-lang French --source-locale en-us
```

### Common locale codes

| Language | Locale code | Archive name |
|----------|-------------|-------------|
| English | `en-us` | `lang_en_text.archive` |
| Turkish | `tr-tr` | `lang_tr_text.archive` |
| Russian | `ru-ru` | `lang_ru_text.archive` |
| Japanese | `ja-jp` | `lang_ja_text.archive` |
| Chinese (Simplified) | `zh-cn` | `lang_zh_text.archive` |
| Korean | `ko-kr` | `lang_ko_text.archive` |
| Polish | `pl-pl` | `lang_pl_text.archive` |
| German | `de-de` | `lang_de_text.archive` |
| French | `fr-fr` | `lang_fr_text.archive` |
| Spanish | `es-es` | `lang_es_text.archive` |
| Italian | `it-it` | `lang_it_text.archive` |
| Portuguese (Brazil) | `pt-br` | `lang_pt_text.archive` |
| Czech | `cz-cz` | `lang_cz_text.archive` |
| Hungarian | `hu-hu` | `lang_hu_text.archive` |
| Arabic | `ar-ar` | `lang_ar_text.archive` |
| Thai | `th-th` | `lang_th_text.archive` |

> **Important:** The source language must be installed in your game. Check your game's language settings (Steam: right-click game > Properties > Language) and make sure the source language is downloaded.

### Why Turkish as the default source?

Kazakh and Turkish are both Turkic languages with near-identical grammar (agglutinative morphology, SOV word order, vowel harmony). This produces significantly better LLM translations than English > Kazakh, and Turkish UI string lengths closely match what Kazakh needs, reducing UI overflow issues.

For other target languages, English (`en-us`) is usually the best source since LLMs have the most training data for English.

## Usage

```powershell
# Activate venv (every new terminal session)
.venv\Scripts\Activate.ps1

# Full pipeline: extract > translate > repack
cp2077-translate --config config.toml

# Extract strings only (preview before spending API credits)
cp2077-translate --config config.toml --extract-only

# Resume an interrupted translation run (reuses extracted files)
cp2077-translate --config config.toml --skip-extract

# Apply existing translations without re-translating
cp2077-translate --config config.toml --skip-extract --skip-translate

# Translate only, skip archive repacking (for testing)
cp2077-translate --config config.toml --skip-repack

# Override the LLM model
cp2077-translate --config config.toml --model claude-sonnet-4-20250514

# Use OpenAI instead of Anthropic
cp2077-translate --config config.toml --provider openai --model gpt-4o

# Smaller batch size (use if you hit token limits on long strings)
cp2077-translate --config config.toml --batch-size 20

# Test run: only translate 5 strings end-to-end
cp2077-translate --config config.toml --limit 5

# Fast re-test (skip extraction on subsequent runs)
cp2077-translate --config config.toml --limit 5 --skip-extract

# All options
cp2077-translate --help
```

### CLI Reference

| Flag | Description |
|------|-------------|
| `--config`, `-c` | Path to `config.toml` (required) |
| `--provider` | API provider: `anthropic` (default) or `openai` |
| `--source-lang` | Source language name, overrides config |
| `--target-lang` | Target language name, overrides config |
| `--source-locale` | Source locale directory, overrides config |
| `--api-key` | API key, overrides config and env var |
| `--model` | LLM model name, overrides config (auto-corrected if mismatched with provider) |
| `--batch-size` | Strings per API call, overrides config |
| `--extract-only` | Extract strings to CSV and stop (no API calls) |
| `--skip-extract` | Skip archive extraction, reuse existing files |
| `--skip-translate` | Skip translation, apply existing `translation_log.csv` |
| `--skip-repack` | Skip repacking (translate but don't build archive) |
| `--limit` | Only process the first N strings (for testing) |

## Pipeline Steps

| Step | What happens |
|------|-------------|
| **1. Extract** | Finds and unpacks the source locale archive (e.g. `lang_tr_text.archive`) via WolvenKit CLI, then converts CR2W binary files to human-readable JSON |
| **2. Extract strings** | Walks the JSON files and collects every `femaleVariant` and `maleVariant` dialogue string with its metadata |
| **3. Translate** | Sends strings to the LLM API (Anthropic or OpenAI) in configurable batches with dialogue context (speaker, scene); saves progress to `translation_log.csv` after each batch |
| **4. Apply** | Writes translated strings back into the JSON files, replacing the originals |
| **5. Repack** | Converts the patched JSON files back to CR2W binary, then packs everything into a `.archive` mod file |

Progress is saved after every batch in Step 3. If the run is interrupted (network error, rate limit, crash), re-run the same command and it will resume from where it left off.

## Installing the Mod

After the pipeline completes, it prints the location of the output `.archive` file(s).

### Step 1: Find the archive

The repacked `.archive` file(s) are in the `work/` directory (alongside the `extracted/` folder):

```
work/
  extracted/          <-- intermediate files (can be deleted)
  extracted.archive   <-- this is your mod file
```

### Step 2: Copy to game

Copy the `.archive` file(s) into your game's mod directory:

```
<Cyberpunk 2077 install folder>/archive/pc/mod/
```

For example:
```powershell
copy work\*.archive "C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077\archive\pc\mod\"
```

> Create the `mod/` folder if it doesn't already exist.

### Step 3: Launch the game

Start Cyberpunk 2077 normally. The game automatically loads `.archive` files from `archive/pc/mod/`. No REDmod deployment or additional tools are needed.

> **Tip:** In-game, go to Settings > Interface > Subtitles and make sure subtitles are enabled to see translated dialogue.

### Uninstalling the mod

Delete the `.archive` file(s) you copied into `archive/pc/mod/`. The game will revert to its original language files.

## Configuration Reference

All settings go in `config.toml`. Every setting has a sensible default; only paths and your API key are required.

```toml
[wolvenkit]
# Path to WolvenKit CLI executable (absolute or relative to config file)
cli_path = "C:\\Tools\\WolvenKit\\WolvenKit.CLI.exe"

[paths]
# Path to Cyberpunk 2077 game installation
game_dir = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Cyberpunk 2077"
# Working directory for extracted and repacked files
work_dir = "./work"
# Output directory for translation log and pipeline logs
output_dir = "./output"

[mod]
# Mod metadata (used in archive naming)
name = "CP2077KazakhTranslation"
version = "1.0.0"
description = "Kazakh translation of Cyberpunk 2077 localization"

[performance]
# Number of parallel workers for CR2W conversion (1-64)
# Higher = faster extraction/repacking, more CPU usage
workers = 8

[translation]
# API provider: "anthropic" (default) or "openai"
provider = "anthropic"
# Source language name (human-readable, used in the LLM translation prompt)
source_lang = "Turkish"
# Target language name (human-readable, used in the LLM translation prompt)
target_lang = "Kazakh"
# Source locale directory in extracted archives (must match the game's locale code)
source_locale = "tr-tr"
# API key (can also be set via ANTHROPIC_API_KEY or OPENAI_API_KEY env var, or --api-key flag)
# api_key = "sk-ant-..."
# LLM model for translation (auto-corrected if mismatched with provider)
model = "claude-sonnet-4-20250514"
# Number of strings per API call (lower = safer for long strings, higher = fewer API calls)
batch_size = 40
```

> **Path resolution:** Relative paths in `config.toml` are resolved relative to the directory containing the config file, not your current working directory.

## Output Files

| Path | Description |
|------|-------------|
| `output/translation_log.csv` | Every translated string with source and target text. Used for resume and auditing. |
| `output/translation_*.log` | Timestamped pipeline log (all steps, warnings, errors). Send this when reporting issues. |
| `work/extracted/` | Intermediate JSON files from archive extraction. Safe to delete after repacking. |
| `work/*.archive` | The final mod file(s) to install in your game. |

### Translation log format

`translation_log.csv` contains one row per translated string:

| Column | Description |
|--------|-------------|
| `filepath` | Source JSON file path |
| `string_key` | Dialogue key (usually `secondaryKey` from the game data) |
| `string_id` | Numeric string ID from the game data |
| `field` | Which variant (`femaleVariant` or `maleVariant`) |
| `source_text` | Original text in the source language |
| `translated_text` | LLM-translated text in the target language |

You can open this CSV in Excel or a text editor to review translations before applying them.

## Troubleshooting

### "No locale files found"
The source language pack is not installed in your game. Go to your game launcher (Steam/GOG/Epic), open the game's language settings, and download the source language.

### "WolvenKit CLI not found"
Set `cli_path` in `config.toml` to the full path to `WolvenKit.CLI.exe`. Make sure you downloaded the **CLI** release, not the GUI application.

### "Response truncated (hit max_tokens)"
Your strings are too long for the current batch size. Reduce `batch_size` in `config.toml` (try `20` or `10`).

### Translation stops mid-run
The pipeline saves progress after every batch. Simply re-run the same command with `--skip-extract` and it will resume from where it stopped. The pipeline retries failed batches up to 3 times with exponential backoff before giving up.

### Translations look wrong
Open `output/translation_log.csv` and review the translations. If a specific batch is bad, delete those rows from the CSV and re-run with `--skip-extract` to re-translate just the missing entries.

### Game text unchanged after installing the mod
- Make sure the `.archive` file is in `archive/pc/mod/`, not in `archive/pc/content/`
- Make sure you're looking at the correct language in-game (the mod replaces the *source* language's text)
- Check that subtitles are enabled in game settings

## Limitations

- **Subtitles only** -- translates on-screen text (subtitles, dialogue, UI). Voice audio remains in the original language.
- **Requires source language pack** -- the game must have the source language installed and downloaded.
- **UI overflow** -- some translations may be longer than the UI element allows. This is inherent to translation and affects high-visibility strings like menu items and tooltips.
- **LLM quality** -- translation quality depends on the model and language pair. Review `translation_log.csv` for critical strings.
- **Windows only** -- WolvenKit CLI requires Windows.

## Disclaimers

**Translation quality is not guaranteed.** This tool uses AI-generated translation, not human review. Mistakes, awkward phrasing, and outright errors will occur -- especially for less common language pairs or context-heavy dialogue. The output is meant as a starting point, not a polished localization. You can hand-edit `translation_log.csv` to fix bad translations and re-run with `--skip-extract --skip-translate` to apply corrections.

**You are responsible for your own API costs.** This tool calls paid API services (Anthropic or OpenAI) using your API key. A full game translation can cost anywhere from ~$4 (gpt-4o-mini) to $400+ (claude-opus) depending on the model you choose. Always use `--extract-only` to preview string counts and `--limit` for small test runs before committing to a full translation. The author of this tool is not responsible for any API charges you incur.
