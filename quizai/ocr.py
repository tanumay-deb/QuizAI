"""Fast on-device OCR via RapidOCR (ONNXRuntime).

This is the primary ingestion layer for the OCR-first routing pipeline: it reads
the text off a screenshot in ~0.3 s, far faster than a vision LLM's CPU-bound
image encoder (~18 s under Ollama). Routing then decides whether the *answer*
needs vision (graphs, diagrams, rendered math) or can be done from text alone.

Design notes (all benchmark-driven):
  - ``use_cls=False`` — screenshots are upright; the angle classifier only adds
    latency and occasionally flips a line into garbage at high confidence.
  - Boxes are re-sorted into reading order by **column then row** (x then y),
    because RapidOCR returns multi-column pages row-interleaved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quizai.logger import get_logger

log = get_logger(__name__)


@dataclass
class OCRLine:
    text: str
    confidence: float
    x: int  # left edge of the box (used for column sorting)
    y: int  # top edge of the box


@dataclass
class OCRResult:
    text: str  # all lines joined in reading order
    mean_confidence: float
    lines: list[OCRLine] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return len(self.text.replace("\n", "").strip())


class OCRReader:
    """Lazy RapidOCR wrapper. Construct cheaply; the model loads on first use."""

    def __init__(self) -> None:
        self._engine = None  # set on first read / warmup

    def _ensure_engine(self) -> None:
        if self._engine is not None:
            return
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "RapidOCR is not installed. Run: pip install rapidocr-onnxruntime"
            ) from e
        self._engine = RapidOCR()

    def warmup(self) -> None:
        """Load the ONNX models ahead of the first real capture. Never raises."""
        try:
            self._ensure_engine()
            import numpy as np

            self._engine(np.zeros((64, 64, 3), dtype="uint8"), use_cls=False)
            log.info("RapidOCR warmed up")
        except Exception as exc:  # best-effort
            log.debug("OCR warmup skipped/failed: %s", exc)

    def read(self, png_bytes: bytes) -> OCRResult:
        """Run OCR on a PNG and return text in column-then-row reading order."""
        self._ensure_engine()
        import io

        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        result, _ = self._engine(np.array(img), use_cls=False)
        if not result:
            return OCRResult(text="", mean_confidence=0.0, lines=[])

        lines: list[OCRLine] = []
        for box, text, score in result:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(
                OCRLine(text=text, confidence=float(score), x=int(min(xs)), y=int(min(ys)))
            )

        ordered = _reading_order(lines)
        text = "\n".join(ln.text for ln in ordered)
        mean_conf = sum(ln.confidence for ln in ordered) / len(ordered)
        return OCRResult(text=text, mean_confidence=mean_conf, lines=ordered)


def _reading_order(lines: list[OCRLine]) -> list[OCRLine]:
    """Sort lines into human reading order, handling multi-column layouts.

    RapidOCR returns multi-column pages row-interleaved (left1, right1, left2…).
    We cluster lines into columns by x-position, then read each column top→bottom,
    left column first. Single-column pages collapse to a plain y-sort.
    """
    if len(lines) <= 1:
        return lines
    xs = sorted(ln.x for ln in lines)
    page_width = max(ln.x for ln in lines) - min(ln.x for ln in lines)
    # If the horizontal spread is small, it's a single column → just sort by y.
    if page_width < 200:
        return sorted(lines, key=lambda ln: ln.y)
    # Detect a column gap: the largest jump between consecutive x-starts.
    gaps = [(xs[i + 1] - xs[i], xs[i]) for i in range(len(xs) - 1)]
    max_gap, split_after = max(gaps, key=lambda g: g[0]) if gaps else (0, 0)
    if max_gap < 120:  # no clear column break → single column
        return sorted(lines, key=lambda ln: ln.y)
    threshold = split_after + max_gap / 2
    left = sorted([ln for ln in lines if ln.x <= threshold], key=lambda ln: ln.y)
    right = sorted([ln for ln in lines if ln.x > threshold], key=lambda ln: ln.y)
    return left + right
