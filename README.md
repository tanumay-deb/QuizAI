# QuizAI Assistant

> Desktop AI study assistant. Capture a quiz or exam question on your screen, get a clear answer and explanation in seconds.

<p align="center">
  <a href="https://github.com/YOUR_USERNAME/quizai-assistant/actions/workflows/ci.yml">
    <img src="https://github.com/YOUR_USERNAME/quizai-assistant/actions/workflows/ci.yml/badge.svg" alt="CI status">
  </a>
  <a href="https://github.com/YOUR_USERNAME/quizai-assistant/releases">
    <img src="https://img.shields.io/github/v/release/YOUR_USERNAME/quizai-assistant" alt="Latest release">
  </a>
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
  <img src="https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Cross-platform">
  <img src="https://img.shields.io/badge/code%20style-ruff-orange" alt="Ruff">
</p>

<!--
  Add a screenshot or GIF here once you have one. Suggested:
  - A capture flow showing the overlay popping up with an answer
  - The main window with history
  - The settings dialog
-->

<!-- ![QuizAI overlay in action](docs/images/overlay.png) -->

## What it does

QuizAI sits quietly in your system tray. When you trigger it — by global hotkey, tray menu, or automatic timer — it captures your screen, sends the image to an AI vision model, extracts any quiz/exam-style question it finds, and shows the answer + explanation in a floating overlay. Every Q&A is saved to a searchable local history.

Useful for:

- Working through practice problems in study PDFs, flashcard apps, or online courses
- Reviewing your own notes or printed material via a screen capture
- Accessibility — getting on-screen text explained when you can't easily read it
- Quick "what does this error mean?" on stack traces and code

Built for **personal study**. Not for use during proctored exams, certifications, or graded coursework — see the [ethical use note](#ethical-use) at the bottom.

## Features

- 🎯 **AI vision detection** — finds quiz-style questions in a screenshot and extracts them verbatim
- 🧠 **Reasoned answers** — every answer comes with a 2–6 sentence explanation
- 📚 **Multi-question handling** — when a screenshot has several questions (e.g. a practice PDF page), use `‹ ›` in the overlay to navigate; each is answered on demand
- ⌨️ **Global hotkeys** — capture, show/hide window, dismiss overlay; all rebindable
- 🔇 **Background system-tray app** — no taskbar clutter, runs silently
- 🪟 **Always-on-top semi-transparent overlay** — draggable, pinnable, auto-hides
- ✍️ **Manual input** — type any question into the main window for an instant answer
- 💾 **Searchable history** — every Q&A saved locally in SQLite, never sent anywhere except the AI provider
- 🔔 **Sound + desktop notifications** — chime on success, error tone on failure (toggleable)
- 🧩 **Pluggable AI providers** — Google Gemini (free tier) and Anthropic Claude out of the box

## Requirements

- Python 3.10 or newer
- An API key — **free Gemini** ([aistudio.google.com/apikey](https://aistudio.google.com/apikey), no card required) or paid Claude
- Windows, macOS, or Linux

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/quizai-assistant
cd quizai-assistant

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -e .
```

If you don't plan to use Claude, edit `pyproject.toml` to remove the `anthropic` dependency line — Gemini-only is significantly smaller.

### Platform-specific setup

| OS | Extra steps |
|---|---|
| **Windows** | None |
| **macOS** | First run prompts for *Screen Recording* and *Accessibility* permissions — grant both |
| **Linux** | `sudo apt install scrot libxcb-cursor0 libpulse0` (covers capture, Qt platform, audio) |

See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) if something doesn't work.

## Setup — free Gemini key

1. Visit [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in with any Google account
2. Click **Create API key** → copy it
3. Run `python -m quizai` — it'll prompt for the key on first launch

Or set it as an env var:

```bash
# macOS / Linux
export GEMINI_API_KEY=AIza...

# Windows PowerShell
$env:GEMINI_API_KEY = "AIza..."
```

## Running

```bash
python -m quizai
# or, after installing:
quizai
```

The app starts minimized to the tray. Right-click the tray icon for the menu.

## Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl + Shift + Q` | Capture screen and analyse |
| `Ctrl + Shift + H` | Show / hide main window |
| `Ctrl + Shift + X` | Dismiss overlay |

All configurable in Settings. Format follows [pynput](https://pynput.readthedocs.io/en/latest/keyboard.html#monitoring-the-keyboard) syntax: `<ctrl>+<shift>+q`, `<cmd>+<alt>+a`, `<f8>`, etc. Leave a field blank to disable that hotkey entirely.

## Building a standalone executable

```bash
pip install -e ".[dev]"
python scripts/build.py
```

Produces `dist/QuizAI(.exe|.app)`. Drop it on your Desktop — double-click to launch. Same command works on Windows, macOS, and Linux.

For auto-launch on Windows login: `Win+R`, type `shell:startup`, drop a shortcut to `QuizAI.exe` in the folder that opens.

## Development

```bash
pip install -e ".[dev]"

# Run tests
pytest

# Lint and format
ruff check . --fix
ruff format .

# Optional: pre-commit hook
pip install pre-commit
pre-commit install
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design tour.

## Project layout

```
quizai-assistant/
├── quizai/                  # main package
│   ├── app.py               # orchestrator
│   ├── overlay.py           # floating window with multi-question paginator
│   ├── main_window.py       # main window + settings
│   ├── tray.py              # system tray
│   ├── notifier.py          # sound + desktop notifications
│   ├── screen_capture.py    # mss-based screenshot
│   ├── hotkey_manager.py    # global hotkeys (pynput)
│   ├── scheduler.py         # auto-capture timer
│   ├── history.py           # SQLite Q&A store
│   ├── config.py            # multi-provider config
│   ├── logger.py            # rotating file logs
│   └── backends/
│       ├── base.py          # Backend interface + parsers
│       ├── gemini_backend.py
│       ├── anthropic_backend.py
│       └── __init__.py      # factory + provider registry
├── tests/                   # pytest suite (67 tests)
├── docs/
│   ├── ARCHITECTURE.md
│   └── TROUBLESHOOTING.md
├── scripts/
│   └── build.py             # PyInstaller wrapper
├── .github/
│   ├── workflows/           # CI + release pipelines
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── quizai.spec              # PyInstaller config
├── pyproject.toml           # packaging + tool config
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── LICENSE
```

## Files & data

- Config: `~/.quizai/config.json`
- History DB: `~/.quizai/history.db`
- Log file: `~/.quizai/quizai.log`
- Sound files: `~/.quizai/sounds/`

Nothing leaves your machine except the AI API calls themselves. No telemetry, no analytics, no remote sync.

## Ethical use

QuizAI is built for personal study, accessibility, and reviewing your own materials. Using it on proctored exams, certifications, or graded coursework you've agreed not to use external aids on is dishonest and violates the rules of nearly every institution. The consequences of getting caught (score cancellation, retest bans, expulsion) are far worse than just doing the work honestly.

What I won't accept in this repo: features designed to defeat exam monitoring (screen-capture exclusion flags, anti-detection measures), features that mirror or relay overlay content to a separate device (a common cheating pattern), or bundled API keys.

## License

[MIT](LICENSE) — do what you want with it, attribution appreciated.

## Acknowledgements

Built with [PySide6](https://doc.qt.io/qtforpython/) (Qt), [mss](https://github.com/BoboTiG/python-mss) for fast screenshots, [pynput](https://github.com/moses-palmer/pynput) for global hotkeys, the [Google GenAI SDK](https://googleapis.github.io/python-genai/) and the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
