"""Mobile companion HTTP server.

Serves a dark-themed mobile web page at GET / and pushes new Q&A answers
to connected browsers in real time via Server-Sent Events at GET /events.
GET /answers returns the full accumulated list as JSON (polling fallback).

The server runs on a daemon thread; the Qt main thread calls push_answer()
whenever a new answer arrives.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import queue
import socket
import threading
import uuid

from quizai.logger import get_logger

log = get_logger(__name__)

# ------------------------------------------------------------ mobile HTML page
# Raw string (r"""...""") so backslash sequences in the inline JS regexes pass
# through to the browser verbatim instead of being interpreted by Python.
_MOBILE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuizAI</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117;
    --surface: #181b24;
    --border: #262a36;
    --text: #e8eaf0;
    --muted: #6b7280;
    --accent: #4c84e0;
    --green: #4ade80;
    --error: #f87171;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 15px;
    line-height: 1.5;
    padding: 16px;
    max-width: 640px;
    margin: 0 auto;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 14px;
    margin-bottom: 18px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--bg);
    z-index: 10;
  }
  h1 { font-size: 19px; font-weight: 700; color: #fff; letter-spacing: 0.3px; }
  #status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.6px;
  }
  #dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: #444;
    transition: background 0.3s, box-shadow 0.3s;
  }
  #dot.live { background: var(--green); box-shadow: 0 0 6px rgba(74, 222, 128, 0.5); }
  #dot.err  { background: var(--error); }
  #empty {
    padding: 56px 16px;
    text-align: center;
    color: var(--muted);
    font-size: 14px;
  }
  .spinner {
    display: block;
    width: 32px;
    height: 32px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 16px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .qa {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 14px;
    animation: fadein 0.25s ease;
  }
  @keyframes fadein { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; } }
  .tag {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .tag.a-tag { color: var(--green); }
  .q-text { font-size: 13px; color: #9ca3af; font-style: italic; margin-bottom: 12px; }
  .a-text { font-size: 17px; font-weight: 700; color: #fff; margin-bottom: 10px; }
  .e-text { font-size: 13px; color: #d1d5db; line-height: 1.65; }
  .divider { border: none; border-top: 1px solid var(--border); margin: 4px 0 10px; }
</style>
</head>
<body>
<header>
  <h1>QuizAI</h1>
  <div id="status"><span id="statusText">connecting</span><span id="dot"></span></div>
</header>
<div id="empty"><span class="spinner"></span>Waiting for answers…</div>
<div id="list"></div>
<script>
(function () {
  'use strict';

  var dot        = document.getElementById('dot');
  var statusText = document.getElementById('statusText');
  var empty      = document.getElementById('empty');
  var list       = document.getElementById('list');
  var shown      = Object.create(null);

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>');
  }

  function setStatus(state, text) {
    dot.className = state || '';
    statusText.textContent = text;
  }

  function renderCard(entry) {
    if (!entry || entry.id == null) return;
    var key = String(entry.id);
    if (shown[key]) return;
    shown[key] = true;

    var card = document.createElement('div');
    card.className = 'qa';
    var explanationHtml = '';
    if (entry.explanation) {
      explanationHtml =
        '<hr class="divider">' +
        '<div class="tag">Explanation</div>' +
        '<div class="e-text">' + escapeHtml(entry.explanation) + '</div>';
    }
    card.innerHTML =
      '<div class="tag">Question</div>' +
      '<div class="q-text">' + escapeHtml(entry.question) + '</div>' +
      '<div class="tag a-tag">Answer</div>' +
      '<div class="a-text">' + escapeHtml(entry.answer) + '</div>' +
      explanationHtml;

    // Newest on top.
    list.insertBefore(card, list.firstChild);
    empty.style.display = 'none';
  }

  // ---- Catch-up via /answers (works even if SSE never connects).
  function fetchAll() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/answers', true);
    xhr.onload = function () {
      if (xhr.status !== 200) {
        console.error('GET /answers ->', xhr.status);
        return;
      }
      try {
        var arr = JSON.parse(xhr.responseText);
        if (!Array.isArray(arr)) return;
        // Server returns oldest-first; render in that order so insertBefore puts newest on top.
        for (var i = 0; i < arr.length; i++) renderCard(arr[i]);
      } catch (e) {
        console.error('Failed to parse /answers response', e);
      }
    };
    xhr.onerror = function () { console.error('/answers request failed'); };
    xhr.send();
  }

  // ---- SSE for live push.
  var sseTimer = null;
  function startSSE() {
    if (sseTimer) { clearTimeout(sseTimer); sseTimer = null; }
    setStatus('', 'connecting');
    var es;
    try {
      es = new EventSource('/events');
    } catch (e) {
      setStatus('err', 'no SSE');
      console.error('EventSource ctor threw', e);
      return;
    }
    es.onopen = function () { setStatus('live', 'live'); };
    es.onmessage = function (ev) {
      try {
        renderCard(JSON.parse(ev.data));
      } catch (e) {
        console.error('Bad SSE payload', ev.data, e);
      }
    };
    es.onerror = function () {
      setStatus('err', 'reconnecting');
      try { es.close(); } catch (_) {}
      sseTimer = setTimeout(startSSE, 3000);
    };
  }

  // ---- Periodic safety-net poll. SSE handles the live case; this catches
  //      anything missed if the SSE connection silently drops without erroring.
  function poll() {
    fetchAll();
    setTimeout(poll, 6000);
  }

  fetchAll();
  startSSE();
  setTimeout(poll, 6000);
})();
</script>
</body>
</html>
"""

_HTML_BYTES = _MOBILE_HTML.encode("utf-8")

_MAX_HISTORY = 50  # keep at most this many answers in memory


# ---------------------------------------------------------------- HTTP handler
class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._serve_html()
        elif self.path == "/events":
            self._serve_sse()
        elif self.path == "/answers":
            self._serve_answers()
        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_HTML_BYTES)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(_HTML_BYTES)

    def _serve_answers(self) -> None:
        """Return the full accumulated answer list as JSON array."""
        mobile: MobileServer = self.server._mobile  # type: ignore[attr-defined]
        with mobile._lock:
            body = json.dumps(mobile._qa_list, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_sse(self) -> None:
        mobile: MobileServer = self.server._mobile  # type: ignore[attr-defined]
        client_q: queue.Queue[str] = queue.Queue(maxsize=20)

        # Register and atomically get the current history so the client can
        # catch up on any answers that arrived before the SSE connection.
        catch_up = mobile._register_client(client_q)
        for item in catch_up:
            try:
                client_q.put_nowait(item)
            except queue.Full:
                break

        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            while True:
                try:
                    data = client_q.get(timeout=25)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Heartbeat keeps connection alive through NAT / proxies.
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            mobile._deregister_client(client_q)

    def log_message(self, fmt: str, *args: object) -> None:
        log.info("mobile-http: " + fmt, *args)


# ---------------------------------------------------------------- HTTP server
class _ThreadedServer(http.server.ThreadingHTTPServer):
    # ThreadingHTTPServer already sets allow_reuse_address and daemon_threads.

    def __init__(self, addr: tuple, handler, mobile: MobileServer) -> None:
        super().__init__(addr, handler)
        self._mobile = mobile


# --------------------------------------------------------------- public class
class MobileServer:
    """Lightweight SSE broadcast server for the mobile companion."""

    def __init__(self, port: int = 7432) -> None:
        self._port = port
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()
        self._qa_list: list[dict] = []  # full history; each item is a dict
        self._counter: int = 0  # monotonic id within this session
        # Prefix every id with a per-session token so a stale browser tab
        # from a previous run can't dedupe ids from a fresh server.
        self._session: str = uuid.uuid4().hex[:8]
        self._server: _ThreadedServer | None = None

    # ----------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        """Start the server. Returns True on success, False if port is in use."""
        try:
            srv = _ThreadedServer(("0.0.0.0", self._port), _Handler, self)
            self._server = srv
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            log.info("Mobile companion running at %s", self.local_url())
            return True
        except OSError as exc:
            log.error("Mobile companion failed to start on port %d: %s", self._port, exc)
            return False

    def stop(self) -> None:
        if self._server is not None:
            with contextlib.suppress(Exception):
                self._server.shutdown()
            self._server = None
        with self._lock:
            self._clients.clear()

    @property
    def running(self) -> bool:
        return self._server is not None

    # ----------------------------------------------------------------- push
    def push_answer(self, question: str, answer: str, explanation: str) -> None:
        """Append a new Q&A and broadcast it to all connected browsers."""
        with self._lock:
            self._counter += 1
            entry = {
                "id": f"{self._session}-{self._counter}",
                "question": question,
                "answer": answer,
                "explanation": explanation,
            }
            self._qa_list.append(entry)
            if len(self._qa_list) > _MAX_HISTORY:
                self._qa_list = self._qa_list[-_MAX_HISTORY:]

            payload = json.dumps(entry, ensure_ascii=False)
            dead: list[queue.Queue[str]] = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._clients.remove(q)

        log.info("Mobile: pushed answer id=%s to %d SSE client(s)", entry["id"], len(self._clients))

    # ----------------------------------------------------------------- client management
    def _register_client(self, q: queue.Queue[str]) -> list[str]:
        """Add client to broadcast list; return serialised history for catch-up."""
        with self._lock:
            self._clients.append(q)
            history = [json.dumps(e, ensure_ascii=False) for e in self._qa_list]
            log.info(
                "Mobile: SSE client connected (total=%d, history=%d items)",
                len(self._clients),
                len(history),
            )
            return history

    def _deregister_client(self, q: queue.Queue[str]) -> None:
        with self._lock:
            try:
                self._clients.remove(q)
                log.info("Mobile: SSE client disconnected (total=%d)", len(self._clients))
            except ValueError:
                pass

    # ----------------------------------------------------------------- URL
    def local_url(self) -> str:
        return f"http://{_get_local_ip()}:{self._port}"


# -------------------------------------------------------------- helpers
def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
