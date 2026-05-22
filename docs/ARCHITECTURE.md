# Architecture

A tour of how QuizAI Assistant is put together, for contributors and curious readers.

## High-level shape

```
                    ┌────────────────────────┐
                    │     QApplication       │
                    │  (Qt main event loop)  │
                    └────────────┬───────────┘
                                 │
                       ┌─────────▼──────────┐
                       │     QuizAIApp      │  ← orchestrator
                       │  (owns everything) │
                       └─────────┬──────────┘
                                 │
       ┌────────────┬────────────┼────────────┬─────────────┐
       │            │            │            │             │
  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐  ┌───▼─────┐  ┌────▼─────┐
  │  Tray   │  │ Window  │  │ Overlay │  │ Hotkeys │  │ Scheduler│
  │  (UI)   │  │  (UI)   │  │  (UI)   │  │ (daemon)│  │ (daemon) │
  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └──────────┘

                       ┌──────────▼──────────┐
                       │  ApiWorker QThread  │
                       │   (single worker)   │
                       └──────────┬──────────┘
                                  │
                       ┌──────────▼──────────┐
                       │       Backend       │  ← pluggable
                       │  (Gemini, Claude…)  │
                       └─────────────────────┘
```

## Threading model

The single hardest thing in a desktop AI app is keeping the UI responsive while waiting on slow network calls. QuizAI uses three independent threads, all owned by the orchestrator:

### 1. Qt main thread

Owns every widget. Period. If you ever find yourself calling `.show()` or `.setText()` from another thread, you'll get either silent no-ops or crashes. Everything UI-related — overlay, window, tray, settings dialog — runs here.

### 2. ApiWorker thread (`QThread`)

A long-lived worker that processes one job at a time. The orchestrator emits `_job_requested(job)` from the main thread; via `Qt.QueuedConnection`, that signal hops onto the worker thread where `ApiWorker.run_job(job)` runs synchronously. When the AI call completes, the worker emits `answer_ready` / `api_error` / `no_question_found` — which hop back to the main thread the same way.

Why a single worker rather than a thread pool? Because the UI assumes "busy" is a global state — when one capture is in flight, the user can't trigger another. Concurrent jobs would complicate the state machine for ~no gain (most users won't run more than one query at once anyway).

The **only** exception: paginator lazy-answers run "concurrently" with each other in the sense that the user can fire several before any completes. The worker still processes them serially (one at a time on its single thread), but the UI doesn't lock during them — each one carries its `index` field so the answer can be routed to the right overlay slot when it arrives.

### 3. Background daemons

- **AutoCaptureScheduler** — A `threading.Thread` that wakes up on its interval and triggers a screen capture. It never touches Qt directly; it uses `QMetaObject.invokeMethod(..., QueuedConnection)` to schedule `_on_capture_requested` on the main thread.
- **HotkeyManager (pynput)** — pynput spawns its own listener thread internally. We wrap callbacks in `_invoke_in_qt` which uses `QTimer.singleShot(0, fn)` to hop back to the main thread.

The pattern is the same in both cases: **non-Qt thread → marshal back to Qt thread → touch widgets**.

## Module map

| Module | Responsibility | Threads it touches |
|---|---|---|
| `app.py` | Orchestrator. Wires every component, owns lifecycle. | Main + signals to worker |
| `backends/` | LLM provider abstraction. Each backend implements `detect_and_extract_question` + `answer_question`. | Worker only |
| `config.py` | Persisted settings + env-var resolution + v1→v2 migration. | Any (pure data) |
| `history.py` | SQLite-backed Q&A store. | Any (uses a write lock) |
| `screen_capture.py` | mss-based screenshot, downscaled for API efficiency. | Main (blocks briefly) |
| `overlay.py` | Always-on-top frameless window. Owns paginator state. | Main only |
| `main_window.py` | Main window + settings dialog. | Main only |
| `tray.py` | `QSystemTrayIcon` + menu. Generated icon, no assets. | Main only |
| `notifier.py` | Synth chime + tray notifications. | Main only |
| `hotkey_manager.py` | pynput global hotkeys. | pynput thread |
| `scheduler.py` | Auto-capture timer. | Daemon thread |
| `logger.py` | Rotating file + stderr logging setup. | Any |

## Backend abstraction

A `Backend` is anything that implements:

```python
class Backend(ABC):
    def detect_and_extract_question(self, png_bytes: bytes) -> DetectionResult: ...
    def answer_question(self, question: str) -> AnswerResult: ...
```

Backends are registered in `backends/__init__.py:PROVIDER_INFO`. To add a new one:

1. Create `backends/<name>_backend.py` implementing `Backend`.
2. Register it in `PROVIDER_INFO` with a label, default model list, and key-help string.
3. Add it to the factory `create_backend()` (a two-line addition).
4. Add an optional dependency in `pyproject.toml` if the provider needs its own SDK.

That's it — no other module needs to change. The settings dialog, the orchestrator, and the worker all use the `Backend` interface only.

## The "no question found" path

This is worth calling out because it's the one place the API is allowed to say "nothing to answer here." The flow:

1. User triggers capture (hotkey, tray, button, auto-timer).
2. `app.py` grabs PNG bytes via `screen_capture.capture()`.
3. Worker calls `backend.detect_and_extract_question(png)`.
4. If `det.has_question` is false (or the questions list is empty), worker emits `no_question_found`.
5. Orchestrator clears `_busy`, overlay shows the error message, notifier plays the error tone.

The detection prompt is engineered to err on the side of "no" for ambiguous content — UI screenshots without an explicit question prompt should not trigger a useless answer.

## Configuration & migration

`config.py` uses a dataclass with explicit defaults. Two design choices worth noting:

1. **Per-provider keys**: `gemini_api_key` and `anthropic_api_key` are stored separately, not as one "current" key. This means the user can switch providers without losing the other key. `effective_api_key()` returns the one for the currently-selected provider, with env vars taking precedence.

2. **Forward-compatible loading**: `Config.from_dict()` ignores unknown keys (so a newer config file loaded by an older app version doesn't crash) and provides v1 migration (the original schema had a single `api_key` and `model` — those are mapped to the Anthropic slot of the new dict).

## Persistent storage layout

```
~/.quizai/
├── config.json    # user settings
├── history.db     # SQLite, WAL mode
├── quizai.log     # rotating (1 MB × 3 backups)
└── sounds/        # synthesized chime + error tones, created on first run
    ├── chime.wav
    └── error.wav
```

Nothing is encrypted. The API key sits in plain JSON; treat the file like any other credential. OS keyring integration is a possible future enhancement.
