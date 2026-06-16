"""Text-LLM question extraction + answering from OCR text (Ollama).

One call does the whole text path: read the OCR'd page, extract each question
verbatim, classify whether answering needs the image, and answer the textual
ones. Answer-only (no long explanations) — benchmarks showed explanations blow
generation time from ~4 s to ~13 s; explanations can be fetched lazily later.

Returns a list of QAItem. Items with ``requires_visual_context=True`` carry no
answer and signal the worker to escalate the capture to the vision model.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from quizai.logger import get_logger

log = get_logger(__name__)

DEFAULT_HOST = "http://localhost:11434"
_TIMEOUT_S = 120.0

_SYSTEM = (
    "You are given raw OCR text from a quiz/exam screenshot. Extract EVERY question "
    "verbatim, including its answer choices. For each question decide whether answering "
    "REQUIRES seeing an image/graph/figure/diagram/table that the OCR text cannot convey. "
    "If it does, set requires_visual_context=true and answer=null. Otherwise answer it "
    "concisely (for multiple choice give the letter AND the option text, e.g. 'B. 12'; "
    "for numeric give the value). Do NOT include long explanations.\n"
    'Reply ONLY with JSON: {"questions":[{"question":str,"requires_visual_context":bool,'
    '"answer":str|null,"confidence":number}]}'
)


@dataclass
class QAItem:
    question: str
    answer: str
    requires_visual_context: bool
    confidence: float


def extract_and_answer(
    ocr_text: str,
    model: str,
    host: str = DEFAULT_HOST,
    num_ctx: int = 8192,
    keep_alive: str = "30m",
) -> list[QAItem]:
    """Run the one-call extract+classify+answer. Raises on transport/parse errors."""
    host = (host or "").strip().rstrip("/") or DEFAULT_HOST
    if "://" not in host:
        host = "http://" + host
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": keep_alive,
        "think": False,  # suppress thinking-mode latency on models like qwen3
        "options": {"temperature": 0.0, "num_predict": 1500, "num_ctx": num_ctx},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "OCR TEXT:\n" + ocr_text + "\n/no_think"},
        ],
    }
    raw = _post(f"{host}/api/chat", body)
    try:
        content = json.loads(raw).get("message", {}).get("content", "") or ""
        data = json.loads(content)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"text model returned unparseable JSON: {raw[:200]}") from exc

    items: list[QAItem] = []
    for q in (data or {}).get("questions", []) or []:
        if not isinstance(q, dict):
            continue
        question = str(q.get("question", "") or "").strip()
        if not question:
            continue
        needs_vis = bool(q.get("requires_visual_context", False))
        answer = "" if needs_vis else str(q.get("answer") or "").strip()
        try:
            conf = float(q.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        items.append(
            QAItem(
                question=question,
                answer=answer,
                requires_visual_context=needs_vis,
                confidence=conf,
            )
        )
    return items


def _post(url: str, body: dict) -> str:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Could not reach Ollama at {url}: {exc.reason}") from exc
