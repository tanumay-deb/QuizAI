# Contributing to QuizAI Assistant

Thanks for considering a contribution! This document covers the basics.

## Getting set up

```bash
git clone https://github.com/tanumay-deb/quizai-assistant
cd quizai-assistant
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

That installs the app in editable mode plus the dev tools (`pytest`, `ruff`, `pyinstaller`, etc.).

### Platform extras

- **Linux**: `sudo apt install scrot libxcb-cursor0 libpulse0` (for capture, Qt platform plugin, audio)
- **macOS**: nothing extra, but grant Screen Recording + Accessibility permissions on first run
- **Windows**: nothing extra

## Running the app

```bash
python -m quizai
# or, after installing:
quizai
```

## Running tests

```bash
pytest                    # all tests
pytest tests/test_config.py -v   # one file, verbose
pytest --cov=quizai       # with coverage
```

Tests that need Qt run headlessly via `QT_QPA_PLATFORM=offscreen` (set automatically by `conftest.py`). They don't open windows or make network calls.

## Style

We use [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting.

```bash
ruff check .          # lint
ruff check . --fix    # auto-fix what's safe
ruff format .         # format
```

CI runs both on every push. If you'd like, install the pre-commit hook so it runs on every commit:

```bash
pip install pre-commit
pre-commit install
```

## How to add a new feature

The codebase has a few hot spots most features touch:

- **A new LLM provider** → add a file in `quizai/backends/`, register it in `backends/__init__.py:PROVIDER_INFO`. Implement the `Backend` interface from `backends/base.py`.
- **A new hotkey** → add a `Config` field in `config.py`, a `QLineEdit` in `SettingsDialog`, a binding in `QuizAIApp._apply_hotkeys()`.
- **A new setting** → add a `Config` field, a widget in `SettingsDialog`, read it in `result_config()`, and apply it in `QuizAIApp._on_settings_changed()`.
- **A new overlay state** → add a method on `OverlayWindow` (`show_*`), follow the existing thinking/error/answer pattern.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a tour of the threading model and module boundaries.

## Commits and PRs

- Keep commits focused; one logical change per commit when practical.
- PR titles in imperative mood: "Add Gemini Flash-Lite to model list", not "Added…" or "Adds…".
- If the change is user-visible, add a line to `CHANGELOG.md` under `[Unreleased]`.
- New behaviour gets a test. New parser code definitely gets a test.

## Reporting bugs

Open an issue with:
- OS + version
- Python version (`python --version`)
- Which AI provider you're using
- Whether it's reproducible — and steps if so
- The relevant chunk of `~/.quizai/quizai.log` if there's an error trace

## Things we won't accept

- Features designed to defeat exam-monitoring software (screen-capture exclusion flags, hidden processes, anti-detection measures).
- Features that mirror or relay the overlay content to a separate device.
- Bundled API keys.

These restrictions exist because this tool is for personal study; it's not a cheating tool. Please don't ask.

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Short version: be kind, assume good faith, no harassment.
