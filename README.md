# CP2077 Translation Pipeline

CLI toolchain that extracts localization text from Cyberpunk 2077 game archives, translates it to another language using an LLM API (Claude), and repacks the result as an installable mod.

## What This Does

- **Extracts** all translatable strings (subtitles, dialogue, UI text) from any supported source locale
- **Translates** via LLM API in batches, preserving character tone, markup tags, and variable placeholders
- **Repacks** translated text into a game-ready `.archive` mod
- Covers both the **base game** and **Phantom Liberty** expansion
- **Resumable** — interrupted translation runs can be continued without re-translating completed batches

### Why Turkish → Kazakh?

The default configuration translates from Turkish because Kazakh and Turkish are both Turkic languages with near-identical grammar (agglutinative, SOV, vowel harmony). This produces much better translations than English → Kazakh, and Turkish UI string lengths closely match what Kazakh will need.

---

## Prerequisites

| Tool | Purpose | Where to get |
|------|---------|--------------|
| **Python 3.11+** | Runs the pipeline | [python.org](https://www.python.org/downloads/) |
| **WolvenKit CLI** | Extracts/repacks CP2077 archives | [GitHub Releases](https://github.com/WolvenKit/WolvenKit/releases) |
| **Anthropic API key** | Powers the LLM translation | [console.anthropic.com](https://console.anthropic.com/) |

> WolvenKit CLI is Windows-only. The pipeline must run on Windows.

---

## Setup

```powershell
git clone <repo-url>
cd cp2077-translate
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Copy and edit the config:
```powershell
copy config.toml.example config.toml
notepad config.toml
```

Set your API key (pick one method):
```powershell
# Option A: environment variable
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Option B: in config.toml under [translation]
# api_key = "sk-ant-..."
```

---

## Usage

```powershell
# Activate venv (every new terminal)
.venv\Scripts\activate

# Full pipeline: extract → translate → repack
cp2077-translate translate --config config.toml

# Extract strings only (preview before spending API credits)
cp2077-translate translate --config config.toml --extract-only

# Resume an interrupted translation run
cp2077-translate translate --config config.toml --skip-extract

# Apply existing translations without re-translating
cp2077-translate translate --config config.toml --skip-extract --skip-translate

# Translate from a different source language
cp2077-translate translate --config config.toml --source-lang Russian --source-locale ru-ru

# All options
cp2077-translate translate --help
```

---

## Pipeline Steps

| Step | What happens |
|------|-------------|
| **1. Extract** | Unpacks locale archive (e.g. `lang_tr_text.archive`) via WolvenKit, converts CR2W → JSON |
| **2. Extract strings** | Walks JSON files and collects every `femaleVariant`/`maleVariant` string |
| **3. Translate** | Sends batches to the LLM API with dialogue context; saves progress to `translation_log.csv` |
| **4. Apply** | Writes translated strings back into the JSON files |
| **5. Repack** | Converts JSON back to CR2W, repacks into `.archive` |

---

## Installing the Mod

1. Copy the `.archive` file(s) from `work/` to:
   ```
   <Cyberpunk 2077>/archive/pc/mod/
   ```
2. Launch the game — no REDmod deployment needed.

To uninstall, delete the `.archive` file(s) from `archive/pc/mod/`.

---

## Configuration

```toml
[wolvenkit]
cli_path = "C:\\Tools\\WolvenKit\\WolvenKit.CLI.exe"

[paths]
game_dir = "C:\\Games\\Cyberpunk 2077"
work_dir = "./work"
output_dir = "./output"

[mod]
name = "CP2077KazakhTranslation"

[performance]
workers = 8

[translation]
source_lang = "Turkish"
target_lang = "Kazakh"
source_locale = "tr-tr"
# api_key = "sk-ant-..."    # or set ANTHROPIC_API_KEY env var
model = "claude-sonnet-4-20250514"
batch_size = 40
```

---

## Output Files

| File | Description |
|------|-------------|
| `output/translation_log.csv` | Every translated string (source → target) for auditing and resume |
| `output/translation_*.log` | Timestamped pipeline log |
| `work/extracted/` | Intermediate JSON files — safe to delete after repacking |

---

## Limitations

- **Subtitles only** — translates on-screen text; voice audio remains in the original language
- **Requires source language pack** — the game must have the source language installed (e.g. Turkish)
- **UI overflow** — some translations may be longer than the UI element allows; review high-visibility strings
