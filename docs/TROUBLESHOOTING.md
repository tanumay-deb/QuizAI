# Troubleshooting

Common issues and how to fix them. If your problem isn't here, open an issue with the contents of `~/.quizai/quizai.log`.

## Installation

### `error: command 'gcc' failed` on Linux during pip install

You're missing build tools. On Ubuntu/Debian:

```bash
sudo apt install build-essential python3-dev
```

### `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` on Linux

Missing the X11 client libraries Qt needs. On Ubuntu/Debian:

```bash
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libxcb-sync1 libxcb-xfixes0 libxcb-xinerama0
```

### `pip install` succeeds but `python -m quizai` does nothing on macOS

Most likely you're on macOS 13+ and haven't granted permissions yet. Open **System Settings → Privacy & Security → Screen Recording**, find your terminal (or Python itself), and tick the box. Restart the app. You may also need **Accessibility** ticked for global hotkeys.

## Runtime

### "Invalid Gemini API key"

The key isn't being read correctly. Things to check:

1. The key really does start with `AIza…` and was copied without extra whitespace.
2. If you set `GEMINI_API_KEY` as an env var, env vars take precedence — make sure the env var isn't stale.
3. The key hasn't been disabled at https://aistudio.google.com/apikey.

### "Gemini free-tier quota hit"

You've hit Gemini's per-minute or per-day rate limit. Either wait a minute or upgrade your AI Studio project to a paid tier. Setting auto-capture to a longer interval (60+ seconds) helps avoid this during long study sessions.

### Hotkeys don't fire on macOS

macOS requires **Accessibility** permission to send keystrokes to background apps. Open **System Settings → Privacy & Security → Accessibility** and tick whichever Python (or QuizAI.app) you're running. Restart the app.

### Hotkeys don't fire on Wayland (Linux)

Wayland intentionally blocks global hotkey capture for security reasons. You have two options:

1. Switch to an Xorg session at login.
2. Use the system tray menu or the main window's "Capture screen now" button instead.

### The overlay never appears

Open the main window from the tray and check whether the answer is appearing in the History panel. If yes, your overlay opacity may be too low — open Settings and bump *Overlay opacity* up to 0.95. If no answers are appearing at all, check `~/.quizai/quizai.log` for API errors.

### Tray icon is missing

- **macOS**: it's in the top menu bar, not the Dock.
- **Ubuntu (GNOME)**: install the AppIndicator extension or check that "icons in tray" are enabled.
- **Windows**: the icon might be hidden in the overflow ⌃ menu — click that to find it, then drag it onto the visible portion of the tray.

### Sound plays but is cut off / scratchy

QtMultimedia uses different audio backends per OS. On Linux, install `libpulse0` and `libasound2`; on Windows and macOS the built-in backends are reliable.

## Packaging

### PyInstaller binary fails to launch with no error

Run it from a terminal to see the actual exception:

```bash
# macOS
./dist/QuizAI.app/Contents/MacOS/QuizAI

# Linux
./dist/QuizAI

# Windows (cmd or PowerShell)
.\dist\QuizAI.exe
```

The most common cause is a missing hidden import — add it to the `HIDDEN` list in `quizai.spec` and rebuild.

### Windows Defender flags the .exe as a virus

False positive. PyInstaller binaries trip several AV products' heuristics because the same packaging tool is also used by malware authors. Options:

1. Add an exclusion in Windows Defender for your build folder.
2. Sign the binary with a code-signing certificate (~$200/year from a CA).
3. Submit the binary to Microsoft for analysis at https://www.microsoft.com/wdsi/filesubmission — they usually whitelist within a few days.

### Antivirus blocks the build itself

Some antivirus products quarantine PyInstaller's bootloader before it's even copied into your `dist/`. Pause real-time protection during the build, or whitelist your project directory.

## Diagnostics

`~/.quizai/quizai.log` rotates at 1 MB × 3 backups. It logs every API call, error, and significant state change. If you're reporting a bug, attach the last 200 lines.

To bump the log level temporarily:

```python
# In quizai/logger.py, change:
setup_logging(level=logging.DEBUG)
```

Or set the env var `PYTHONLOGLEVEL=DEBUG` before running.
