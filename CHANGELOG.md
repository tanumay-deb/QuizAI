# Changelog

All notable changes to QuizAI Assistant are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] — 2026-06-16

### Added
- **OCR-first routing (local)** — when using Ollama, screenshots are read with RapidOCR (~0.3 s) and routed: textual questions answered by a fast text model, only genuinely visual ones (charts/diagrams) escalated to the vision model. Cuts local capture latency from ~18–24 s to ~3–5 s. New `quizai/ocr.py`, `quizai/routing.py`, `quizai/text_qa.py`.
- **Single-call cloud screen reader** — cloud providers (Gemini) now answer a whole capture in **one** request (OCR text + image → extract + answer all), instead of detect + N answers. Easier on free-tier rate limits. New `Backend.answer_screen`.
- **OpenAI-compatible backend** — point QuizAI at OpenAI, Groq, OpenRouter, or LM Studio via Base URL + key.
- **Resizable overlay** — drag the corner to resize; size persists across captures and restarts.
- **Per-capture telemetry + OCR cache** — one `CAPTURE` log line per capture (route/confidence/latency); identical re-captures reuse OCR results.
- **Windows standalone executable + npm launcher** — download `QuizAI.exe` from Releases, or install in one go with `npx github:tanumay-deb/QuizAI`.

### Changed / Fixed
- Ollama performance: startup model warm-up, `keep_alive`, and pinned `num_ctx` (ignores the desktop app's huge default context that overflowed VRAM).
- Settings spinbox increase (▲) buttons are now clickable (QSS sub-control fix).
- Repo-wide `ruff` lint + format cleanup; stale overlay/config tests fixed.

## [1.2.0] — 2026-05-28

### Added
- **Ollama local-LLM backend** — run vision + reasoning entirely on your own machine, no API costs, nothing leaves the host. New provider "Ollama (local, private, free)" in Settings. Default model `qwen2.5vl:7b` (~4.7 GB, fits in 8 GB VRAM); other curated options include `minicpm-v:8b`, `llama3.2-vision:11b`, `gemma3:4b`, and the larger `qwen2.5vl:32b` for 24 GB+ rigs.
- The API-key field becomes a plain-text "Host URL" field when Ollama is selected (default `http://localhost:11434`).
- `OLLAMA_HOST` env var honoured as a fallback when the host field is blank.

### Changed
- `Config` gains `ollama_host` (default `http://localhost:11434`); `effective_api_key()` returns the host for the Ollama provider so the existing "is the backend configured?" gates work unchanged.
- `_refresh_for_provider()` in the Settings dialog now drives field label / echo mode / help-text URL linking off per-provider metadata in `PROVIDER_INFO`, instead of hardcoding "API key".

### Backend / internal
- New `quizai/backends/ollama_backend.py` — vision + text via the Ollama HTTP `/api/chat` endpoint. Uses `"format": "json"` for the detection prompt to force valid structured output. No SDK dependency (stdlib `urllib`).

## [1.1.0] — 2026-05-28

### Added
- **Follow-up / conversational mode** — select any history entry and ask a follow-up; the previous Q&A is forwarded to the model as context. New `Backend.answer_question(question, context=…)` signature; both Gemini and Anthropic backends updated.
- **Multi-monitor picker UI** — Settings now lists every detected monitor (with resolution & position) in a combo box instead of a numeric spinbox.
- **Question cache** — identical (normalised) questions answered in the last 7 days are served instantly from `history.db` without an API call. Toggle and TTL configurable in Settings → Question cache.
- **Detection cache** — back-to-back captures of the same screen reuse the last vision result for up to 1 hour (in-memory LRU(8) keyed by PNG SHA-256), saving the vision call entirely.
- **Telegram group access policy** — `Telegram chat ID(s)` now accepts a comma/whitespace-separated allowlist. Outgoing answers broadcast to every id; incoming messages still only honoured from allowlisted chats.
- **History pane upgrades** — filter by source (screen / manual / Telegram), search across explanation text as well as question & answer, and **Export…** the visible entries to Markdown or CSV.

### Changed
- `list_entries()` accepts a `source` filter and now searches the explanation column too.
- Telegram notifier broadcasts to multiple chat ids; each send logs success or failure per recipient.

### Backend / internal
- `quizai.history` gains `question_hash()` and `find_cached_answer()`.
- `quizai.screen_capture` gains `list_monitors()` returning `MonitorInfo` records.
- `quizai.backends.base` gains `build_followup_prompt()` for composing the user turn when context is supplied.
- New `_FollowUpJob` dispatched on the existing ApiWorker thread.

## [1.0.0] — 2026-05-21

### Added
- System-tray desktop app with floating semi-transparent overlay
- Pluggable AI backend layer supporting Google Gemini (free tier) and Anthropic Claude
- Vision-based detection: capture a screenshot and Claude/Gemini extract the question
- Manual question input from the main window
- Multi-question handling — overlay paginator (`‹ 1 / 3 ›`) when several questions are extracted from one screenshot; each answer fetched lazily as the user navigates
- Sound + desktop notifications for answer-ready and error events; sounds are synthesized in Python on first run (no asset files)
- Persistent SQLite history with full-text-style search, individual delete, clear-all
- Global hotkeys (capture, toggle window, dismiss overlay) — all configurable
- Per-monitor screen capture selection
- Auto-capture scheduler with configurable interval (off by default)
- Per-provider API key storage with environment-variable override (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`)
- Settings dialog covering all options with live re-application
- Config schema migration from v1 single-provider layout
- PyInstaller spec file and build script for Windows / macOS / Linux binaries
- GitHub Actions CI for tests and binary releases on tag push
- Pytest suite covering parsers, config, history, scheduler, and the backend factory

### Security
- API keys stored in plain JSON at `~/.quizai/config.json`. Treat that file like any other credential file — set file permissions appropriately on shared machines. (Consider OS keyring integration in a future release.)
