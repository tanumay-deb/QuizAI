"""Screen capture utilities built on top of mss.

mss is fast, cross-platform, and dependency-light. We hand back PNG bytes
ready to be base64-encoded for the Claude API.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import mss
import mss.tools
from PIL import Image

from quizai.logger import get_logger

log = get_logger(__name__)

# Hard cap to keep request payloads small. Claude Vision is happy at this size
# and it dramatically reduces base64 overhead vs. a 4K screenshot.
MAX_DIM = 1568


@dataclass
class Screenshot:
    png_bytes: bytes
    width: int
    height: int


def capture(monitor_index: int = 0) -> Screenshot:
    """Capture the screen.

    monitor_index = 0  -> all monitors stitched together (mss index 0)
    monitor_index = N  -> Nth monitor (mss indices 1..N)
    """
    with mss.mss() as sct:
        monitors = sct.monitors  # [0] is the "all" virtual monitor
        if not monitors:
            raise RuntimeError("No monitors detected by mss")
        if monitor_index < 0 or monitor_index >= len(monitors):
            log.warning(
                "Invalid monitor index %d; falling back to 0 (all monitors)",
                monitor_index,
            )
            monitor_index = 0
        mon = monitors[monitor_index]
        raw = sct.grab(mon)
        # mss returns BGRA; convert to a PIL Image (RGB).
        img = Image.frombytes("RGB", raw.size, raw.rgb)

    img = _downscale(img, MAX_DIM)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    png = buf.getvalue()
    log.debug("Captured screen: %dx%d, %d bytes png", img.width, img.height, len(png))
    return Screenshot(png_bytes=png, width=img.width, height=img.height)


def _downscale(img: Image.Image, max_dim: int) -> Image.Image:
    """Downscale so the longest edge <= max_dim. Preserves aspect ratio."""
    w, h = img.size
    longest = max(w, h)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)
