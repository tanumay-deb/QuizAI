# Changelog

All notable changes to QuizAI Assistant are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
