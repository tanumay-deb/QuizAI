"""Mobile companion HTTP server.

Serves a dark-themed mobile web page at GET / and pushes new Q&A answers
to connected browsers via Server-Sent Events at GET /events.

The server runs on a daemon thread; the Qt main thread calls push_answer()
whenever a new answer arrives.
"""

from __future__ import annotations

import http.server
import json
import queue
import socket
import socketserver
import threading
from typing import Optional

from quizai.logger import get_logger

log = get_logger(__name__)

# ------------------------------------------------------------ mobile HTML page
_MOBILE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>QuizAI</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#0f1117;--surface:#181b24;--border:#262a36;
    --text:#e8eaf0;--muted:#6b7280;--accent:#4c84e0;--green:#86efac;
  }
  body{
    background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-size:15px;line-height:1.5;
    padding:16px;max-width:640px;margin:0 auto;
  }
  header{
    display:flex;align-items:center;justify-content:space-between;
    padding-bottom:14px;margin-bottom:18px;border-bottom:1px solid var(--border);
  }
  h1{font-size:19px;font-weight:700;color:#fff;letter-spacing:0.3px}
  #dot{
    width:9px;height:9px;border-radius:50%;background:#444;
    transition:background 0.4s;
  }
  #dot.live{background:#4ade80;box-shadow:0 0 6px #4ade8088}
  #dot.err{background:#f87171}
  #waiting{
    padding:56px 0;text-align:center;color:var(--muted);font-size:14px;
  }
  #waiting::before{
    content:'';display:block;width:32px;height:32px;
    border:3px solid var(--border);border-top-color:var(--accent);
    border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px;
  }
  @keyframes spin{to{transform:rotate(360deg)}}
  #qa{display:none}
  .card{
    background:var(--surface);border:1px solid var(--border);
    border-radius:14px;padding:16px 18px;margin-bottom:12px;
  }
  .tag{
    font-size:10px;font-weight:700;letter-spacing:1px;
    text-transform:uppercase;color:var(--muted);margin-bottom:8px;
  }
  .tag.a-tag{color:var(--green)}
  .q-text{font-size:14px;color:#9ca3af;font-style:italic}
  .a-text{font-size:18px;font-weight:700;color:#fff}
  .e-text{font-size:14px;color:#d1d5db}
</style>
</head>
<body>
<header><h1>QuizAI</h1><span id="dot"></span></header>
<div id="waiting">Waiting for an answer…</div>
<div id="qa">
  <div class="card"><div class="tag">Question</div><div class="q-text" id="q"></div></div>
  <div class="card"><div class="tag a-tag">Answer</div><div class="a-text" id="a"></div></div>
  <div class="card" id="ec"><div class="tag">Explanation</div><div class="e-text" id="e"></div></div>
</div>
<script>
(function(){
  var dot=document.getElementById('dot'),
      waiting=document.getElementById('waiting'),
      qa=document.getElementById('qa'),
      ec=document.getElementById('ec'),
      qEl=document.getElementById('q'),
      aEl=document.getElementById('a'),
      eEl=document.getElementById('e');
  function connect(){
    var es=new EventSource('/events');
    es.onopen=function(){dot.className='live'};
    es.onmessage=function(ev){
      var d=JSON.parse(ev.data);
      qEl.textContent=d.question;
      aEl.textContent=d.answer;
      if(d.explanation){eEl.textContent=d.explanation;ec.style.display=''}
      else{ec.style.display='none'}
      waiting.style.display='none';
      qa.style.display='';
    };
    es.onerror=function(){dot.className='err';es.close();setTimeout(connect,3000)};
  }
  connect();
}());
</script>
</body>
</html>
"""

_HTML_BYTES = _MOBILE_HTML.encode("utf-8")


# ---------------------------------------------------------------- HTTP handler
class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._serve_html()
        elif self.path == "/events":
            self._serve_sse()
        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_HTML_BYTES)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(_HTML_BYTES)

    def _serve_sse(self) -> None:
        mobile: MobileServer = self.server._mobile  # type: ignore[attr-defined]
        client_q: queue.Queue[str] = queue.Queue(maxsize=20)

        # Register the client and atomically capture the latest payload so no
        # answer can slip between registration and the initial send.
        latest = mobile._register_client(client_q)
        if latest:
            try:
                client_q.put_nowait(latest)
            except queue.Full:
                pass

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
                    # Heartbeat keeps the connection alive through proxies / NAT.
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            mobile._deregister_client(client_q)

    def log_message(self, fmt: str, *args: object) -> None:
        log.debug("mobile-http " + fmt, *args)


# ---------------------------------------------------------------- TCP server
class _ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr: tuple, handler, mobile: "MobileServer") -> None:
        super().__init__(addr, handler)
        self._mobile = mobile


# --------------------------------------------------------------- public class
class MobileServer:
    """Lightweight SSE broadcast server for the mobile companion."""

    def __init__(self, port: int = 7432) -> None:
        self._port = port
        self._clients: list[queue.Queue[str]] = []
        self._lock = threading.Lock()
        self._latest: Optional[str] = None
        self._server: Optional[_ThreadedServer] = None

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
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
        with self._lock:
            self._clients.clear()

    @property
    def running(self) -> bool:
        return self._server is not None

    # ----------------------------------------------------------------- push
    def push_answer(self, question: str, answer: str, explanation: str) -> None:
        """Broadcast a new Q&A to all connected browsers. Thread-safe."""
        payload = json.dumps(
            {"question": question, "answer": answer, "explanation": explanation},
            ensure_ascii=False,
        )
        with self._lock:
            self._latest = payload
            dead: list[queue.Queue[str]] = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._clients.remove(q)

    # ----------------------------------------------------------------- client management
    def _register_client(self, q: queue.Queue[str]) -> Optional[str]:
        """Add client queue and return the current latest payload (atomic)."""
        with self._lock:
            self._clients.append(q)
            return self._latest

    def _deregister_client(self, q: queue.Queue[str]) -> None:
        with self._lock:
            try:
                self._clients.remove(q)
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
