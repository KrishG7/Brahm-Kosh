"""
Cross-platform polling file watcher.

Pure stdlib — no `watchdog` dependency, no platform-specific bindings.
Walks the project once per `interval`, snapshots (mtime, size) per file,
and fires `on_change` when the snapshot differs from the previous one.

Latency is `interval` seconds (default 1.0). Bursts of writes inside one
interval coalesce into a single `on_change` call automatically because
the snapshot only sees the final state.

For >10k-file projects this becomes slow (stat() per file) and you'd want
inotify/FSEvents via watchdog instead. For everything else it's fine.
"""

from __future__ import annotations

import os
import threading
from typing import Callable


# Same skip set the adapters use — no point watching venv or .git.
_SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", "out",
    "target", "vendor", ".next", ".nuxt", ".cache", ".parcel-cache",
    ".idea", ".vscode", "coverage", ".dart_tool", "bin", "obj",
}


def _should_skip_dir(name: str) -> bool:
    return name.startswith(".") or name in _SKIP_DIRS


class PollingWatcher:
    """Polls `root` once per `interval` and calls `on_change(changed_paths)`
    on diff, where `changed_paths` is the list of files that were added,
    removed, or whose (mtime, size) changed since the last poll."""

    def __init__(
        self,
        root: str,
        on_change: Callable[[list[str]], None],
        interval: float = 1.0,
    ):
        self.root = os.path.abspath(root)
        self.on_change = on_change
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="brahm-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        last = self._snapshot()
        while not self._stop.wait(self.interval):
            current = self._snapshot()
            if current == last:
                continue
            changed = self._diff(last, current)
            last = current
            try:
                self.on_change(changed)
            except Exception:
                # Don't kill the watcher on a single bad refresh —
                # the next change will trigger another attempt.
                pass

    @staticmethod
    def _diff(before: dict, after: dict) -> list[str]:
        """Files added, removed, or whose (mtime, size) changed."""
        changed: set[str] = set()
        for path, sig in after.items():
            if before.get(path) != sig:
                changed.add(path)
        for path in before:
            if path not in after:
                changed.add(path)
        return sorted(changed)

    def _snapshot(self) -> dict[str, tuple[float, int]]:
        snap: dict[str, tuple[float, int]] = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            for f in filenames:
                if f.startswith("."):
                    continue
                p = os.path.join(dirpath, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                snap[p] = (st.st_mtime, st.st_size)
        return snap
