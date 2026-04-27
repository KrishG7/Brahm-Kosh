"""
Local Web Server for Brahm-Kosh 3D Interface.

Binds to 127.0.0.1 only. Mutating endpoints require a same-origin request
(Origin header check) plus a per-session CSRF token injected into the
served HTML at load time.

When started with watch=True, a polling file watcher re-runs the analysis
on any file change and pushes a `refresh` event over Server-Sent Events
to every connected browser, which then refetches the graph.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import webbrowser
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from brahm_kosh.models import Project
from brahm_kosh.analysis.architect import analyze_structure
from brahm_kosh.analysis.impact import compute_full_impact
from brahm_kosh.analysis.narrator import generate_narration
from brahm_kosh.analysis.refactor import suggest_splits
from brahm_kosh.analysis.symbol_impact import (
    build_symbol_usage_index,
    compute_symbol_impact,
    per_file_symbol_counts,
)
from brahm_kosh.engine import analyze
from brahm_kosh.watcher import PollingWatcher


# ---------------------------------------------------------------------------
# Graph payload — pulled out as a free function so we can rebuild on refresh
# ---------------------------------------------------------------------------

def _build_graph_payload(project: Project) -> dict:
    """Flatten the hierarchical Project into a node/link payload for the
    3D force graph. Dedupes structural edges so siblings don't double-emit."""
    nodes = []
    links = []
    folders_tracked: set[str] = set()
    structural_edges: set[tuple[str, str]] = set()

    def add_structural(src: str, tgt: str):
        key = (src, tgt)
        if key in structural_edges:
            return
        structural_edges.add(key)
        links.append({"source": src, "target": tgt, "type": "structural"})

    for fm in project.all_files():
        nodes.append({
            "id": fm.relative_path,
            "name": fm.name,
            "type": "file",
            "parent": os.path.dirname(fm.relative_path) or "root",
            "val": fm.complexity + 1,
            "heat": fm.heat_label,
            "purpose": fm.purpose,
            "language": fm.language,
            "symbols": [s.name for s in fm.symbols],
            "narration": generate_narration(fm),
            "domains": sorted(fm.domains) if fm.domains else [],
            "line_count": fm.line_count,
        })

        for dep in fm.dependencies:
            # usage_count: count how many raw_import strings in this file
            # reference the target, as a heuristic for coupling strength.
            dep_stem = os.path.splitext(os.path.basename(dep))[0]
            dep_name = os.path.basename(dep)
            usage_count = max(1, sum(
                1 for imp in fm.raw_imports
                if dep_stem in imp or dep_name in imp
            ))
            links.append({
                "source": fm.relative_path,
                "target": dep,
                "type": "dependency",
                "usage_count": usage_count,
            })

        parts = fm.relative_path.split("/")
        current_path = ""
        for i in range(len(parts) - 1):
            folder_name = parts[i]
            parent_path = current_path or "root"
            current_path = f"{current_path}/{folder_name}" if current_path else folder_name
            if current_path not in folders_tracked:
                folders_tracked.add(current_path)
                nodes.append({
                    "id": current_path,
                    "name": folder_name,
                    "type": "folder",
                    "parent": parent_path,
                    "val": 15,
                    "heat": "Low",
                })
            add_structural(parent_path, current_path)

        parent_dir = os.path.dirname(fm.relative_path) or "root"
        add_structural(parent_dir, fm.relative_path)

    nodes.append({
        "id": "root",
        "name": project.name or "Repository",
        "type": "folder",
        "parent": None,
        "val": 20,
        "heat": "Optimal",
    })

    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------------------
# SSE client + broadcaster — thread-safe per-client writes
# ---------------------------------------------------------------------------

class _SSEClient:
    """One open SSE connection. send() is safe to call from multiple threads;
    a per-client lock serializes writes so heartbeats and broadcasts can't
    interleave bytes on the same wfile."""

    def __init__(self, wfile):
        self.wfile = wfile
        self.lock = threading.Lock()
        self.alive = True

    def send(self, event: str, data: dict) -> bool:
        if not self.alive:
            return False
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
        with self.lock:
            try:
                self.wfile.write(msg)
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.alive = False
                return False


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that swallows benign client-disconnect errors.

    Browsers routinely open speculative TCP connections (preconnect, parallel
    pipelining) and drop them without sending a request, and SSE clients
    disconnect on tab close. socketserver's default `handle_error` logs the
    full traceback for every one of those, which is just noise — every real
    request still succeeds. We filter only the specific exception types that
    mean "the client went away."
    """

    def handle_error(self, request, client_address):
        exc_type = sys.exc_info()[0]
        benign = (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)
        if exc_type and issubclass(exc_type, benign):
            return
        super().handle_error(request, client_address)


class EventBroadcaster:
    def __init__(self):
        self._clients: list[_SSEClient] = []
        self._lock = threading.Lock()

    def register(self, client: _SSEClient) -> None:
        with self._lock:
            self._clients.append(client)

    def unregister(self, client: _SSEClient) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)

    def broadcast(self, event: str, data: dict) -> None:
        with self._lock:
            survivors = []
            for c in self._clients:
                if c.send(event, data):
                    survivors.append(c)
            self._clients = survivors

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)


# ---------------------------------------------------------------------------
# Mutable server state
# ---------------------------------------------------------------------------

class _AppState:
    """Shared, lock-guarded state attached to the HTTPServer instance."""

    def __init__(self, project: Project, frontend_dir: str, allowed_origins: set[str], csrf_token: str):
        self.project = project
        self.frontend_dir = frontend_dir
        self.allowed_origins = allowed_origins
        self.csrf_token = csrf_token
        self.graph_data = _build_graph_payload(project)
        self.architecture_data = analyze_structure(project)
        self.file_index = {fm.relative_path: fm for fm in project.all_files()}
        # Symbol-level usage index — built once per refresh so per-symbol
        # impact queries are O(1) lookups on hot path.
        self.symbol_index = build_symbol_usage_index(project)
        self.broadcaster = EventBroadcaster()
        self.refresh_lock = threading.Lock()
        self.last_refresh = time.time()


# ---------------------------------------------------------------------------
# Main server
# ---------------------------------------------------------------------------

class ProjectGraphServer:
    def __init__(
        self,
        project: Project,
        port: int = 8080,
        host: str = "127.0.0.1",
        watch: bool = False,
        open_browser: bool = True,
    ):
        self.project = project
        self.port = port
        self.host = host
        self.watch = watch
        self.open_browser = open_browser
        self.frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        self.csrf_token = secrets.token_urlsafe(32)
        self._watcher: PollingWatcher | None = None

        self.state = _AppState(
            project=project,
            frontend_dir=self.frontend_dir,
            allowed_origins={
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            },
            csrf_token=self.csrf_token,
        )

    # Re-analyze the project from disk and push a refresh event.
    # `changed_paths` (absolute) lets the frontend show "3 files updated:
    # X, Y, Z" — surfaced via SSE.
    def refresh(self, changed_paths: list[str] | None = None) -> None:
        with self.state.refresh_lock:
            project, _ = analyze(self.project.path, top_n=100)
            self.state.project = project
            self.state.graph_data = _build_graph_payload(project)
            self.state.architecture_data = analyze_structure(project)
            self.state.file_index = {fm.relative_path: fm for fm in project.all_files()}
            self.state.symbol_index = build_symbol_usage_index(project)
            self.state.last_refresh = time.time()

        # Convert absolute paths from the watcher into project-relative ones
        # so the frontend can match them against graph node ids.
        rel_changed: list[str] = []
        if changed_paths:
            root = os.path.abspath(self.project.path)
            for p in changed_paths:
                try:
                    rel = os.path.relpath(p, root)
                    if not rel.startswith(".."):
                        rel_changed.append(rel)
                except ValueError:
                    continue

        self.state.broadcaster.broadcast("refresh", {
            "ts": self.state.last_refresh,
            "changed": rel_changed,
        })

    def start(self):
        state = self.state
        project_root = Path(self.project.path).resolve()
        frontend_dir = self.frontend_dir
        allowed_origins = state.allowed_origins
        csrf_token = self.csrf_token

        class APIHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=frontend_dir, **kwargs)

            # ---- helpers --------------------------------------------------
            def _send_json(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _origin_ok(self) -> bool:
                origin = self.headers.get("Origin")
                if origin is None:
                    return True
                return origin in allowed_origins

            def _resolve_under_root(self, rel: str) -> Path | None:
                if not rel or rel.startswith(("/", "\\")) or ".." in rel.split("/"):
                    return None
                try:
                    candidate = (project_root / rel).resolve()
                except (OSError, ValueError):
                    return None
                try:
                    candidate.relative_to(project_root)
                except ValueError:
                    return None
                return candidate

            # ---- OPTIONS --------------------------------------------------
            def do_OPTIONS(self):
                self.send_response(204)
                self.end_headers()

            # ---- GET ------------------------------------------------------
            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                params = parse_qs(parsed.query)

                if path == "/api/graph":
                    self._send_json(state.graph_data)
                    return

                if path == "/api/architecture":
                    self._send_json(state.architecture_data)
                    return

                if path == "/api/events":
                    self._serve_sse()
                    return

                if path == "/api/file":
                    self._serve_file(params)
                    return

                if path == "/api/impact":
                    self._serve_impact(params)
                    return

                if path == "/api/symbol-impact":
                    self._serve_symbol_impact(params)
                    return

                if path in ("/", "/index.html"):
                    self._serve_index_with_token()
                    return

                return super().do_GET()

            # ---- /api/file ------------------------------------------------
            def _serve_file(self, params):
                rel = params.get("path", [None])[0]
                if not rel:
                    self.send_error(400, "Missing ?path= parameter")
                    return
                abs_path = self._resolve_under_root(rel)
                if abs_path is None or not abs_path.is_file():
                    self.send_error(404, f"File not found: {rel}")
                    return
                try:
                    source = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    self.send_error(500, str(e))
                    return

                fm = state.file_index.get(rel)

                # Pre-compute per-symbol cross-file usage counts so the
                # Symbols sidebar can show "🔗 N" badges next to each one.
                sym_use_counts = (
                    per_file_symbol_counts(rel, fm.symbols, state.symbol_index)
                    if fm else {}
                )

                def sym_dict(s):
                    return {
                        "name": s.name,
                        "kind": s.kind.value,
                        "line_start": s.line_start,
                        "line_end": s.line_end,
                        "complexity": round(s.complexity, 1),
                        "heat": s.heat_label,
                        "branch_count": s.branch_count,
                        "nesting_depth": s.nesting_depth,
                        "calls": s.calls,
                        "docstring": s.docstring or "",
                        "usage_count": sym_use_counts.get(s.name, 0),
                        "children": [sym_dict(c) for c in s.children],
                    }

                payload = {
                    "path": rel,
                    "name": os.path.basename(rel),
                    "language": fm.language if fm else "Unknown",
                    "line_count": fm.line_count if fm else source.count("\n"),
                    "complexity": round(fm.complexity, 1) if fm else 0,
                    "heat": fm.heat_label if fm else "Low",
                    "purpose": fm.purpose if fm else "",
                    "dependencies": fm.dependencies if fm else [],
                    "dependents": fm.dependents if fm else [],
                    "domains": sorted(fm.domains) if fm and fm.domains else [],
                    "narration": generate_narration(fm) if fm else "",
                    "source": source,
                    "symbols": [sym_dict(s) for s in fm.symbols] if fm else [],
                    "refactor": (
                        [c.to_dict() for c in suggest_splits(fm)] if fm else []
                    ),
                }
                self._send_json(payload)

            # ---- /api/impact?path=... -------------------------------------
            def _serve_impact(self, params):
                rel = params.get("path", [None])[0]
                if not rel:
                    self.send_error(400, "Missing ?path= parameter")
                    return
                if rel not in state.file_index:
                    self.send_error(404, f"Not in project: {rel}")
                    return
                payload = compute_full_impact(rel, state.project)
                self._send_json(payload)

            # ---- /api/symbol-impact?file=...&symbol=... -------------------
            def _serve_symbol_impact(self, params):
                rel = params.get("file", [None])[0]
                sym = params.get("symbol", [None])[0]
                if not rel or not sym:
                    self.send_error(400, "Missing ?file= or ?symbol= parameter")
                    return
                if rel not in state.file_index:
                    self.send_error(404, f"Not in project: {rel}")
                    return
                payload = compute_symbol_impact(rel, sym, state.symbol_index)
                self._send_json(payload)

            # ---- /api/events (SSE) ----------------------------------------
            def _serve_sse(self):
                # Origin gate: only same-origin pages should subscribe.
                if not self._origin_ok():
                    self.send_error(403, "Bad origin")
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                client = _SSEClient(self.wfile)
                state.broadcaster.register(client)
                client.send("hello", {"ts": time.time(), "watch": bool(self.server.watch_enabled)})
                try:
                    # Heartbeats every 15s; failed write flips client.alive.
                    while client.alive:
                        time.sleep(15)
                        client.send("ping", {"ts": time.time()})
                finally:
                    state.broadcaster.unregister(client)

            # ---- index.html with CSRF token injected ----------------------
            def _serve_index_with_token(self):
                index_path = Path(frontend_dir) / "index.html"
                try:
                    html = index_path.read_text(encoding="utf-8")
                except OSError:
                    self.send_error(500, "index.html missing")
                    return

                meta_tag = f'<meta name="brahm-token" content="{csrf_token}">'
                if "<head>" in html:
                    html = html.replace("<head>", f"<head>\n    {meta_tag}", 1)
                else:
                    html = meta_tag + html

                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            # ---- POST /api/save -------------------------------------------
            def do_POST(self):
                if urlparse(self.path).path != "/api/save":
                    self.send_error(404)
                    return

                if not self._origin_ok():
                    self._send_json({"ok": False, "error": "Bad origin"}, 403)
                    return

                token = self.headers.get("X-Brahm-Token", "")
                if not secrets.compare_digest(token, csrf_token):
                    self._send_json({"ok": False, "error": "Bad token"}, 403)
                    return

                ctype = self.headers.get("Content-Type", "")
                if "application/json" not in ctype:
                    self._send_json({"ok": False, "error": "Expected JSON"}, 415)
                    return

                length = int(self.headers.get("Content-Length", 0) or 0)
                if length <= 0 or length > 10 * 1024 * 1024:
                    self._send_json({"ok": False, "error": "Bad length"}, 413)
                    return

                try:
                    data = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    self._send_json({"ok": False, "error": "Bad JSON"}, 400)
                    return

                rel = data.get("path", "")
                new_source = data.get("source", "")
                if not isinstance(rel, str) or not isinstance(new_source, str) or not rel:
                    self._send_json({"ok": False, "error": "Bad payload"}, 400)
                    return

                abs_path = self._resolve_under_root(rel)
                if abs_path is None:
                    self._send_json({"ok": False, "error": "Path traversal denied"}, 403)
                    return
                if rel not in state.file_index:
                    self._send_json({"ok": False, "error": "Unknown file"}, 403)
                    return

                try:
                    abs_path.write_text(new_source, encoding="utf-8")
                except OSError as e:
                    self._send_json({"ok": False, "error": str(e)}, 500)
                    return

                self._send_json({"ok": True, "saved": rel})

            def log_message(self, format, *args):
                pass  # keep CLI clean

        httpd = _QuietThreadingHTTPServer((self.host, self.port), APIHandler)
        httpd.daemon_threads = True
        httpd.state = self.state            # noqa: shared mutable state
        httpd.watch_enabled = self.watch    # noqa: read-only flag

        url = f"http://{self.host}:{self.port}"
        watch_str = " (watching)" if self.watch else ""
        print(f"\n🚀 Brahm-Kosh 3D Server running{watch_str}!")
        print(f"👉 Open {url} in your browser.")
        print(f"📡 API Endpoints:")
        print(f"   GET  {url}/api/graph")
        print(f"   GET  {url}/api/architecture")
        print(f"   GET  {url}/api/file?path=<relative_path>")
        print(f"   GET  {url}/api/events  (SSE)")
        print(f"   POST {url}/api/save  (requires X-Brahm-Token header)")
        if self.watch:
            print(f"\n🔄 Watch mode: edits in {self.project.path} will live-update.")
        print(f"\nPress Ctrl+C to stop the server...\n")

        if self.watch:
            self._watcher = PollingWatcher(self.project.path, self.refresh, interval=1.0)
            self._watcher.start()

        if self.open_browser:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            if self._watcher:
                self._watcher.stop()
            httpd.server_close()


def serve_project(
    project: Project,
    port: int = 8080,
    host: str = "127.0.0.1",
    watch: bool = False,
    open_browser: bool = True,
):
    ProjectGraphServer(project, port, host, watch=watch, open_browser=open_browser).start()
