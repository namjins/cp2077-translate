# CP2077 Translation Pipeline

## Testing

**Always run tests after making code changes:**
```bash
python -m pytest tests/ -v --tb=short
```

All tests must pass before committing.

## Key Rules

- Always identify files by **full relative depot path**, never by basename alone — basename collisions exist across locale directories
- Use `atomic_write()` from fileutil.py for all file output that must survive crashes
- For git commits, switch the model to haiku first

## Project Structure

- `cp2077_translate/` — pipeline source code
  - `extractor.py` — WolvenKit archive extraction and CR2W conversion
  - `translator.py` — string extraction, LLM translation, and application
  - `repacker.py` — CR2W deserialization and archive repacking
  - `packager.py` — zip packaging for mod distribution
  - `config.py` — TOML config loading
  - `fileutil.py` — atomic file write utility
  - `main.py` — CLI entry point
- `tests/` — pytest test suite
- `config.toml` — runtime configuration (not tracked)
- `config.toml.example` — example configuration
