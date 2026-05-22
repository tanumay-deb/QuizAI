"""Sound and notification helpers.

Sound: a short synthesised WAV played via QSoundEffect. The chime is
generated in pure Python on first use and cached on disk so QSoundEffect
gets a proper file:// URL. No external audio assets needed.

Notifications: thin facade over the existing tray. Centralising the logic
here means the rest of the app can call notifier.notify(...) /
notifier.chime(...) without caring which sub-system is doing the work.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from quizai.logger import get_logger

log = get_logger(__name__)


_SOUND_DIR = Path.home() / ".quizai" / "sounds"
_CHIME_PATH = _SOUND_DIR / "chime.wav"
_ERROR_PATH = _SOUND_DIR / "error.wav"


def _synth_tone(
    path: Path,
    *,
    freqs: list[float],
    duration_s: float = 0.18,
    sample_rate: int = 44_100,
    volume: float = 0.35,
) -> None:
    """Write a short multi-tone WAV with linear fade-out. Idempotent."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    n_samples = int(duration_s * sample_rate)
    frames = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        # Mix the requested frequencies; equal weight then normalise.
        sample = sum(math.sin(2 * math.pi * f * t) for f in freqs) / max(1, len(freqs))
        # Linear fade-out across the second half to avoid clicks.
        fade = 1.0 if i < n_samples / 2 else max(0.0, 1.0 - (i - n_samples / 2) / (n_samples / 2))
        val = int(sample * volume * fade * 32_767)
        frames += struct.pack("<h", val)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))


def _ensure_sounds() -> None:
    """Create chime and error sounds if they don't exist on disk yet."""
    try:
        # Pleasant two-note chime — C5 + E5.
        _synth_tone(_CHIME_PATH, freqs=[523.25, 659.25], duration_s=0.22)
        # Lower, slightly dissonant error tone — A3 + Bb3.
        _synth_tone(_ERROR_PATH, freqs=[220.0, 233.08], duration_s=0.28)
    except Exception:
        log.exception("Failed to synthesise notification sounds")


class Notifier(QObject):
    """Owns the QSoundEffect instances and the tray reference."""

    def __init__(self, tray, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._tray = tray
        self._sound_enabled = False
        self._notify_enabled = True
        self._chime = None
        self._error = None
        _ensure_sounds()
        self._init_sound_effects()

    def _init_sound_effects(self) -> None:
        """Lazily import QSoundEffect so a broken multimedia stack doesn't
        crash the whole app — sound just becomes a silent no-op."""
        try:
            from PySide6.QtMultimedia import QSoundEffect  # type: ignore

            if _CHIME_PATH.exists():
                self._chime = QSoundEffect(self)
                self._chime.setSource(QUrl.fromLocalFile(str(_CHIME_PATH)))
                self._chime.setVolume(0.5)
            if _ERROR_PATH.exists():
                self._error = QSoundEffect(self)
                self._error.setSource(QUrl.fromLocalFile(str(_ERROR_PATH)))
                self._error.setVolume(0.5)
        except Exception as e:
            log.warning("QSoundEffect unavailable (%s) — sounds will be silent.", e)

    # ----------------------------------------------------------------- config
    def set_sound_enabled(self, on: bool) -> None:
        self._sound_enabled = bool(on)

    def set_notifications_enabled(self, on: bool) -> None:
        self._notify_enabled = bool(on)

    # ---------------------------------------------------------------- triggers
    def chime(self) -> None:
        """Play the success chime if sounds are enabled."""
        if not self._sound_enabled or self._chime is None:
            return
        try:
            self._chime.play()
        except Exception:
            log.debug("Chime playback failed", exc_info=True)

    def error_sound(self) -> None:
        if not self._sound_enabled or self._error is None:
            return
        try:
            self._error.play()
        except Exception:
            log.debug("Error sound playback failed", exc_info=True)

    def notify(self, title: str, message: str, *, duration_ms: int = 4000) -> None:
        if not self._notify_enabled or self._tray is None:
            return
        try:
            self._tray.notify(title, message, duration_ms=duration_ms)
        except Exception:
            log.debug("Tray notification failed", exc_info=True)
