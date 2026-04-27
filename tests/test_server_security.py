"""
Server security tests.

Exercises the live HTTP server against adversarial inputs:
  - path traversal on /api/file and /api/save
  - CSRF without token
  - cross-origin mutation attempts
  - unknown-file writes
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from brahm_kosh.engine import analyze
from brahm_kosh.server import ProjectGraphServer


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    project, _ = analyze(FIXTURES, top_n=5)
    port = _free_port()
    server = ProjectGraphServer(project, port=port)
    # Patch start() to not open a browser
    import brahm_kosh.server as srv_mod
    srv_mod.webbrowser.open = lambda *a, **kw: None

    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    # Wait for the socket to be ready
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/graph", timeout=1).read()
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("server did not come up")
    yield server, port


def _request(method, url, *, body=None, headers=None):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_graph_endpoint_ok(live_server):
    _, port = live_server
    status, body = _request("GET", f"http://127.0.0.1:{port}/api/graph")
    assert status == 200
    payload = json.loads(body)
    assert "nodes" in payload and "links" in payload


def test_file_endpoint_rejects_traversal(live_server):
    _, port = live_server
    status, _ = _request(
        "GET",
        f"http://127.0.0.1:{port}/api/file?path=../../etc/passwd",
    )
    assert status == 404  # blocked by _resolve_under_root


def test_save_requires_json_content_type(live_server):
    _, port = live_server
    status, _ = _request(
        "POST",
        f"http://127.0.0.1:{port}/api/save",
        body={"path": "py/app.py", "source": "malicious"},
        headers={"Content-Type": "text/plain", "X-Brahm-Token": "whatever"},
    )
    assert status in (403, 415)


def test_save_rejects_bad_origin(live_server):
    _, port = live_server
    status, _ = _request(
        "POST",
        f"http://127.0.0.1:{port}/api/save",
        body={"path": "py/app.py", "source": "pwn"},
        headers={
            "Content-Type": "application/json",
            "Origin": "https://evil.com",
            "X-Brahm-Token": "whatever",
        },
    )
    assert status == 403


def test_save_rejects_missing_token(live_server):
    _, port = live_server
    status, _ = _request(
        "POST",
        f"http://127.0.0.1:{port}/api/save",
        body={"path": "py/app.py", "source": "pwn"},
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
        },
    )
    assert status == 403


def test_save_rejects_unknown_file(live_server):
    server, port = live_server
    status, _ = _request(
        "POST",
        f"http://127.0.0.1:{port}/api/save",
        body={"path": "not-in-project.py", "source": "x"},
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Brahm-Token": server.csrf_token,
        },
    )
    assert status == 403


def test_save_roundtrip_with_valid_token(live_server):
    server, port = live_server
    # Pick a writeable fixture and save it back unchanged
    target = "py/shared.py"
    abs_path = os.path.join(FIXTURES, target)
    original = open(abs_path, encoding="utf-8").read()

    status, body = _request(
        "POST",
        f"http://127.0.0.1:{port}/api/save",
        body={"path": target, "source": original},
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Brahm-Token": server.csrf_token,
        },
    )
    # Restore to be safe
    open(abs_path, "w", encoding="utf-8").write(original)
    assert status == 200, body
    assert json.loads(body)["ok"] is True


def test_index_page_injects_token(live_server):
    _, port = live_server
    status, body = _request("GET", f"http://127.0.0.1:{port}/")
    assert status == 200
    assert b'name="brahm-token"' in body


def test_sse_endpoint_streams_hello_then_refresh(live_server):
    """SSE: connect, read the hello frame, trigger refresh, read refresh frame."""
    server, port = live_server
    import socket

    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.sendall(
        f"GET /api/events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\nAccept: text/event-stream\r\n\r\n".encode()
    )
    # Read until we have at least the hello data line
    s.settimeout(3)
    buf = b""
    deadline = time.time() + 3
    while b"event: hello" not in buf and time.time() < deadline:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    assert b"event: hello" in buf, f"never saw hello frame: {buf!r}"

    # Fire a refresh from the server side and read the broadcast
    server.refresh()
    deadline = time.time() + 3
    while b"event: refresh" not in buf and time.time() < deadline:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    s.close()
    assert b"event: refresh" in buf, f"never saw refresh frame: {buf!r}"


def test_sse_endpoint_rejects_bad_origin(live_server):
    _, port = live_server
    import socket
    s = socket.create_connection(("127.0.0.1", port), timeout=3)
    s.sendall(
        f"GET /api/events HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        f"Origin: https://evil.com\r\nAccept: text/event-stream\r\n\r\n".encode()
    )
    s.settimeout(3)
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = s.recv(4096)
        if not chunk:
            break
        response += chunk
    s.close()
    # First line should be a 4xx
    first_line = response.split(b"\r\n", 1)[0]
    assert b"403" in first_line, f"expected 403, got: {first_line!r}"
