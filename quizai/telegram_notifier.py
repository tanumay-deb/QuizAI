"""Telegram bot notifier.

Sends each Q&A answer to a Telegram chat via the Bot API.
No third-party libraries required — uses only urllib from the standard library.

Setup:
  1. Open Telegram and message @BotFather → /newbot → follow prompts → copy token.
  2. Start a chat with your new bot (send it any message so it can reply to you).
  3. Get your chat_id: message @userinfobot in Telegram → it replies with your ID.
  4. Paste both into Settings → Telegram.
"""

from __future__ import annotations

import html
import json
import threading
import urllib.error
import urllib.request

from quizai.logger import get_logger

log = get_logger(__name__)

_SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_LEN = 4000  # Telegram hard limit is 4096; leave headroom


def _esc(text: str) -> str:
    """HTML-escape text for Telegram's HTML parse mode."""
    return html.escape(str(text))


class TelegramNotifier:
    """Sends quiz answers to a Telegram chat via a bot token."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token.strip()
        self._chat_id = chat_id.strip()

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def send_answer(self, question: str, answer: str, explanation: str) -> None:
        """Fire-and-forget: sends in a daemon thread so Qt is never blocked."""
        if not self.configured:
            return
        threading.Thread(
            target=self._send,
            args=(question, answer, explanation),
            daemon=True,
        ).start()

    def _send(self, question: str, answer: str, explanation: str) -> None:
        parts = [
            f"<b>Q:</b> {_esc(question)}",
            f"\n<b>A:</b> {_esc(answer)}",
        ]
        if explanation:
            parts.append(f"\n\n<i>{_esc(explanation)}</i>")
        text = "".join(parts)
        if len(text) > _MAX_LEN:
            text = text[:_MAX_LEN] + "…"

        payload = json.dumps(
            {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            ensure_ascii=False,
        ).encode("utf-8")

        url = _SEND_URL.format(token=self._token)
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info("Telegram: answer sent (HTTP %d)", resp.status)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            log.error("Telegram: HTTP %d — %s", exc.code, body)
        except Exception:
            log.exception("Telegram: send failed")
