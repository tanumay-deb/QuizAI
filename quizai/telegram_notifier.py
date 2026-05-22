"""Telegram bot notifier.

Sends each Q&A answer to a Telegram chat via the Bot API and listens for
follow-up questions using long polling.
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
import time
import urllib.error
import urllib.request
from typing import Callable

from quizai.logger import get_logger

log = get_logger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/{method}"
_MAX_LEN = 4000  # Telegram hard limit is 4096; leave headroom


def _esc(text: str) -> str:
    """HTML-escape text for Telegram's HTML parse mode."""
    return html.escape(str(text))


class TelegramNotifier:
    """Sends quiz answers to a Telegram chat and listens for follow-up questions."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token.strip()
        self._chat_id = chat_id.strip()
        self._running = False
        self._poll_thread: threading.Thread | None = None
        self._callback: Callable[[str], None] | None = None
        self._offset = 0

    @property
    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def start_polling(self, callback: Callable[[str], None]) -> None:
        if not self.configured:
            return
        self._callback = callback
        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        log.info("Telegram: started polling for messages")

    def stop_polling(self) -> None:
        self._running = False
        if self._poll_thread and self._poll_thread.is_alive():
            # It will exit on its next timeout or network error.
            pass

    def send_answer(self, question: str, answer: str, explanation: str) -> None:
        """Format an answer card and send it."""
        if not self.configured:
            return
        parts = [
            f"<b>Q:</b> {_esc(question)}",
            f"\n<b>A:</b> {_esc(answer)}",
        ]
        if explanation:
            parts.append(f"\n\n<i>{_esc(explanation)}</i>")
        text = "".join(parts)
        self.send_text(text)

    def send_text(self, text: str) -> None:
        """Fire-and-forget raw text sending."""
        if not self.configured:
            return
        threading.Thread(
            target=self._send,
            args=(text,),
            daemon=True,
        ).start()

    def _send(self, text: str) -> None:
        if len(text) > _MAX_LEN:
            text = text[:_MAX_LEN] + "…"

        payload = json.dumps(
            {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            ensure_ascii=False,
        ).encode("utf-8")

        url = _API_URL.format(token=self._token, method="sendMessage")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                log.info("Telegram: message sent (HTTP %d)", resp.status)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            log.error("Telegram: HTTP %d — %s", exc.code, body)
        except Exception:
            log.exception("Telegram: send failed")

    def _poll_loop(self) -> None:
        while self._running:
            try:
                url = _API_URL.format(token=self._token, method=f"getUpdates?offset={self._offset}&timeout=30")
                req = urllib.request.Request(url, method="GET")
                # timeout must be slightly larger than long-polling timeout
                with urllib.request.urlopen(req, timeout=35) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    
                if not data.get("ok"):
                    log.error("Telegram getUpdates error: %s", data)
                    time.sleep(5)
                    continue
                    
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message:
                        continue
                        
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    if chat_id != self._chat_id:
                        log.warning("Telegram: ignored message from unauthorized chat_id: %s", chat_id)
                        continue
                        
                    text = message.get("text", "").strip()
                    if text and self._callback:
                        log.info("Telegram: received message from user")
                        try:
                            self._callback(text)
                        except Exception:
                            log.exception("Telegram: callback failed")
                            
            except urllib.error.URLError as e:
                # This could be a timeout exception, which is perfectly normal for long-polling.
                if hasattr(e, 'reason') and 'time' in str(e.reason).lower():
                    pass
                else:
                    log.debug("Telegram polling network error: %s", e)
                    time.sleep(2)
            except Exception:
                log.exception("Telegram polling exception")
                time.sleep(5)
