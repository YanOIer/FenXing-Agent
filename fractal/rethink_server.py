"""fractal.rethink_server —— 浏览器端「重新思考」按钮使用的本地 HTTP 服务。"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 18920

_agents: dict[str, object] = {}
_lock = threading.RLock()
_server: ThreadingHTTPServer | None = None


def register_agent(agent) -> None:
    """登记当前进程内可被浏览器重新思考的 FractalAgent。"""
    sid = getattr(agent, "session_id", None)
    if not sid:
        return
    with _lock:
        _agents[str(sid)] = agent


def start_rethink_server(host: str = HOST, port: int = PORT) -> tuple[str, int]:
    """幂等启动 localhost HTTP 服务。端口占用时静默降级。"""
    global _server
    with _lock:
        if _server is not None:
            return _server.server_address
        try:
            _server = ThreadingHTTPServer((host, port), _Handler)
        except OSError:
            return host, port
        t = threading.Thread(target=_server.serve_forever, daemon=True)
        t.start()
        return _server.server_address


def rethink_url(session_id: str, node_id: str) -> str:
    return f"http://localhost:{PORT}/rethink?session={session_id}&node={node_id}"


class _Handler(BaseHTTPRequestHandler):
    server_version = "FenXingRethink/1.0"

    def log_message(self, fmt, *args):  # noqa: D401
        """关闭默认 stderr 访问日志，避免污染 REPL。"""

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(200, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/rethink":
            self._send(404, {"ok": False, "error": "not found"})
            return
        qs = parse_qs(parsed.query)
        session_id = (qs.get("session") or [""])[0]
        node_id = (qs.get("node") or [""])[0]
        if not session_id or not node_id:
            self._send(400, {"ok": False, "error": "missing session or node"})
            return
        with _lock:
            agent = _agents.get(session_id)
        if agent is None:
            self._send(404, {"ok": False, "error": "session not found"})
            return
        try:
            result = agent.rethink(node_id)
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return
        if result.get("trace_error") and not result.get("html_path"):
            self._send(400, {"ok": False, "error": result["trace_error"]})
            return
        self._send(200, {
            "ok": True,
            "html_path": result.get("html_path"),
            "json_path": result.get("json_path"),
            "answer": result.get("answer", ""),
            "pending_children": result.get("pending_children", 0),
            "trace_error": result.get("trace_error"),
        })
