# QuizAI Assistant

> Desktop AI study assistant. Capture a quiz or exam question on your screen, get a clear answer and explanation in seconds.

<p align="center">
  <a href="https://github.com/tanumay-deb/quizai-assistant/actions/workflows/ci.yml">
    <img src="https://github.com/tanumay-deb/quizai-assistant/actions/workflows/ci.yml/badge.svg" alt="CI status">
  </a>
  <a href="https://github.com/tanumay-deb/quizai-assistant/releases">
    <img src="https://img.shields.io/github/v/release/tanumay-deb/quizai-assistant" alt="Latest release">
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
- 🧩 **Pluggable AI providers** — Google Gemini (free tier), Anthropic Claude, **Ollama** for fully-local private models (Qwen2.5-VL, MiniCPM-V, Llama 3.2 Vision, Gemma 3, …), and any **OpenAI-compatible** endpoint (OpenAI, Groq, OpenRouter, LM Studio)
- 📱 **Mobile companion** — built-in local web server pushes answers to your phone in real time over Wi-Fi; no extra apps or accounts needed
- 🤖 **Telegram companion** — two-way chat bot: receive answers instantly on Telegram and ask follow-up questions directly from your phone

## Requirements

- **Python 3.10 or newer**
- An **AI key** — a **free Gemini key** works great ([aistudio.google.com/apikey](https://aistudio.google.com/apikey), no credit card). Claude (paid), Ollama (free, runs on your own PC), and any OpenAI-compatible endpoint (OpenAI/Groq/OpenRouter) are also supported.
- **Windows, macOS, or Linux**

## Getting started (step by step)

New to Python or the command line? Follow these in order — copy/paste one command at a time and you'll be running in a few minutes.

### 1. Install Python

QuizAI needs **Python 3.10 or newer**.

| OS | How |
|---|---|
| **Windows** | Download from [python.org/downloads](https://www.python.org/downloads/). In the installer, **tick “Add python.exe to PATH”** before clicking Install. |
| **macOS** | Download from [python.org/downloads](https://www.python.org/downloads/), or run `brew install python` if you have [Homebrew](https://brew.sh). |
| **Linux** | Usually preinstalled. If not: `sudo apt install python3 python3-venv python3-pip` |

Check it worked — open a terminal (see next step) and run:

```bash
python --version
```

You should see `Python 3.10.x` or higher. If you get “command not found”, try `python3 --version` instead, and use `python3` everywhere below.

### 2. Open a terminal

- **Windows** — press `Start`, type **PowerShell**, press Enter.
- **macOS** — press `Cmd + Space`, type **Terminal**, press Enter.
- **Linux** — press `Ctrl + Alt + T`.

This is where you type the commands below.

### 3. Download QuizAI

**If you have [Git](https://git-scm.com):**

```bash
git clone https://github.com/tanumay-deb/quizai-assistant
cd quizai-assistant
```

**If you don't have Git** (easiest for newcomers):

1. Go to [the GitHub page](https://github.com/tanumay-deb/quizai-assistant).
2. Click the green **Code** button → **Download ZIP**.
3. Extract the ZIP somewhere you'll remember (e.g. your Desktop).
4. In your terminal, move into the extracted folder:
   ```bash
   # example — change the path to where you extracted it
   cd Desktop/quizai-assistant-main
   ```

### 4. Create a virtual environment

This keeps QuizAI's dependencies separate from the rest of your system. Run once:

```bash
python -m venv venv
```

Then **activate** it (do this every time you open a new terminal to run QuizAI):

```bash
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

Once active, your prompt shows `(venv)` at the start.

> **Windows note:** if activation fails with a “running scripts is disabled” error, run this once, then try activating again:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### 5. Install QuizAI and its dependencies

```bash
pip install -e .
```

This pulls in everything QuizAI needs — `mss` (screenshots), `PySide6` (the window), and the rest. **This is the step that has to finish before the app will run.** If you skip it, launching the app fails with `ModuleNotFoundError: No module named 'mss'`.

> Don't need Claude? Delete the `anthropic` line from `pyproject.toml` before this step — the install will be noticeably smaller.

### 6. Get a free Gemini key

1. Visit [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in with any Google account.
2. Click **Create API key** → copy it.
3. You'll paste it when the app first launches (next step). No key handy? You can also use **Ollama** for fully-local models — see [Local & private (Ollama)](#local--private-ollama).

(Optional) Instead of pasting in the app, set it as an environment variable:

```bash
# macOS / Linux
export GEMINI_API_KEY=AIza...

# Windows (PowerShell)
$env:GEMINI_API_KEY = "AIza..."
```

### 7. Run it

```bash
python -m quizai
```

The app starts **minimized to your system tray** (near the clock). Right-click the tray icon for the menu, or press `Ctrl + Shift + Q` to capture and analyse the screen. On first launch it'll prompt for your Gemini key if you didn't set the env var.

> After installing, you can also just type `quizai` to launch it (with the venv active).

### Platform-specific setup

| OS | Extra steps |
|---|---|
| **Windows** | None |
| **macOS** | First run prompts for *Screen Recording* and *Accessibility* permissions — grant both |
| **Linux** | `sudo apt install scrot libxcb-cursor0 libpulse0` (covers capture, Qt platform, audio) |

### Common first-run problems

| What you see | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'mss'` (or `PySide6`, etc.) | You skipped step 5 or aren't in the venv. Activate the venv (step 4) and run `pip install -e .` again. |
| `python` not found | Use `python3` instead, or reinstall Python with **Add to PATH** ticked (Windows). |
| PowerShell: *“running scripts is disabled”* | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again (step 4). |
| App launches but says no API key | Paste your Gemini key when prompted, or set `GEMINI_API_KEY` (step 6). |
| Nothing visible after launch | It's in the **system tray**, not a normal window. Look near the clock and right-click the icon. |

Still stuck? See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Local & private (Ollama)

No API key, no cloud — run a vision model entirely on your own machine.

1. Install [Ollama](https://ollama.com/download) and start it (it runs a local server at `http://localhost:11434`).
2. Pull a vision model, e.g.:
   ```bash
   ollama pull qwen2.5vl
   ```
3. In QuizAI, open **Settings**, set the provider to **Ollama**, and pick your model. Leave the host blank to use the default local server.

Everything stays on your PC — nothing is sent to any cloud provider.

> **Speed note:** Ollama runs the model's *vision encoder* on the **CPU**, so reading a screenshot takes ~15–20 s even with the LLM on your GPU. That's a llama.cpp limitation, not your hardware. For faster vision, use a cloud provider (Gemini/Claude/OpenAI-compatible) below.

## OpenAI-compatible providers (OpenAI · Groq · OpenRouter · LM Studio)

QuizAI can talk to **any** server that speaks the OpenAI Chat Completions API. This unlocks both fast local inference and cloud providers beyond Gemini/Claude.

Open **Settings**, set the provider to **OpenAI-compatible**, fill in the **Base URL** + **API key**, and pick a **vision-capable** model:

| Service | Base URL | API key | Example model |
|---|---|---|---|
| **OpenAI** | `https://api.openai.com/v1` | your key | `gpt-4o-mini` |
| **Groq** | `https://api.groq.com/openai/v1` | your key | a Llama-vision model |
| **OpenRouter** | `https://openrouter.ai/api/v1` | your key | any vision model |
| **LM Studio** | `http://localhost:1234/v1` | *(leave blank)* | a loaded vision model |

Self-hosted servers (e.g. LM Studio) may ignore the key, so leave it blank. You can also set `OPENAI_API_KEY` / `OPENAI_BASE_URL` as environment variables instead of using the UI.

## Hotkeys

| Hotkey | Action |
|---|---|
| `Ctrl + Shift + Q` | Capture screen and analyse |
| `Ctrl + Shift + H` | Show / hide main window |
| `Ctrl + Shift + X` | Dismiss overlay |

All configurable in Settings. Format follows [pynput](https://pynput.readthedocs.io/en/latest/keyboard.html#monitoring-the-keyboard) syntax: `<ctrl>+<shift>+q`, `<cmd>+<alt>+a`, `<f8>`, etc. Leave a field blank to disable that hotkey entirely.

## Mobile companion

QuizAI includes a lightweight built-in web server. Whenever an answer arrives on your desktop it is pushed to every connected browser instantly via [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) — no polling, no refresh.

### How to connect

1. Make sure your phone and PC are on the **same Wi-Fi network**
2. Open the QuizAI main window — a link appears below the toolbar:
   ```
   Mobile companion active — open on your phone: http://192.168.x.x:7432
   ```
3. Tap that URL (or type it) in your phone's browser
4. The page updates automatically each time a new answer is ready

The mobile page is dark-themed and shows the question, answer, and explanation in a clean card layout.

### Settings

Open **Settings → Mobile companion** to:

| Option | Default | Description |
|---|---|---|
| Enable mobile companion | On | Toggle the server on/off |
| Mobile port | `7432` | Change if the port is already in use on your machine |

The server only listens on your local network — it is not reachable from the internet.

## Telegram companion

QuizAI features a fully-integrated, two-way Telegram bot. It mirrors every answered question to a private Telegram chat, allowing you to review them on the go. You can also send follow-up questions to the bot, and the AI will answer them right within the chat (while simultaneously showing up on your desktop overlay).

### How to configure

1. Open Telegram and search for **@BotFather**. Send `/newbot`, follow the prompts to create a new bot, and copy the **HTTP API Token** it provides.
2. Search for your newly created bot in Telegram and send it any message (e.g., "Hello") so it can reply to you.
3. Search for **@userinfobot** in Telegram. It will immediately reply with your numeric **Id** (`Chat ID`). Copy this number.
4. On your desktop, open QuizAI, right-click the tray icon, and select **Settings...**.
5. Under the **Telegram bot** section, check **Enable two-way Telegram companion**.
6. Paste your **Telegram bot token** and **Telegram chat ID** into the respective fields and click OK.

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
│   ├── mobile_server.py     # mobile companion (SSE HTTP server)
│   ├── history.py           # SQLite Q&A store
│   ├── config.py            # multi-provider config
│   ├── logger.py            # rotating file logs
│   └── backends/
│       ├── base.py          # Backend interface + parsers
│       ├── gemini_backend.py
│       ├── anthropic_backend.py
│       ├── ollama_backend.py    # local models (vision encoder on CPU)
│       ├── openai_backend.py    # OpenAI-compatible (OpenAI/Groq/OpenRouter)
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

The mobile companion is intended for legitimate study sessions — e.g. reading answers on your phone while working through a practice set at your desk. It connects only over your local Wi-Fi and requires no accounts or external services.

What I won't accept in this repo: features designed to defeat exam monitoring (screen-capture exclusion flags, anti-detection measures) or bundled API keys.

## License

[MIT](LICENSE) — do what you want with it, attribution appreciated.

## Acknowledgements

Built with [PySide6](https://doc.qt.io/qtforpython/) (Qt), [mss](https://github.com/BoboTiG/python-mss) for fast screenshots, [pynput](https://github.com/moses-palmer/pynput) for global hotkeys, the [Google GenAI SDK](https://googleapis.github.io/python-genai/) and the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
