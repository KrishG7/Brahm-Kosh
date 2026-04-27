"""
mtime-based memoization for adapter parse_file functions.

Keying by (module, path, mtime, size) means an unchanged file skips its
adapter's parser entirely on the next call, which is what the engine-level
cache tried to do but couldn't, because by the time it ran, the adapter
had already parsed the file.

Decorate each adapter's `parse_file` with `@memoize_by_mtime` and the
function becomes a no-op on hit. Concurrent-safe (per-module lock).
"""

from __future__ import annotations

import os
import threading
from functools import wraps


_cache: dict[tuple[str, str], tuple[float, int, object]] = {}
_lock = threading.Lock()


def memoize_by_mtime(fn):
    """
    Wrap a `parse_file(file_path, project_root, ...)` function so calls
    with an unchanged (mtime, size) skip parsing entirely.

    Cache is keyed by (`fn.__module__`, file_path) so two adapters that
    both parse `.h` files (e.g. C and a future C++) don't trample each
    other.
    """
    module = fn.__module__

    @wraps(fn)
    def wrapped(file_path, *args, **kwargs):
        try:
            st = os.stat(file_path)
        except OSError:
            return fn(file_path, *args, **kwargs)
        key = (module, file_path)
        with _lock:
            entry = _cache.get(key)
        if entry is not None:
            mtime, size, value = entry
            if mtime == st.st_mtime and size == st.st_size:
                return value
        value = fn(file_path, *args, **kwargs)
        with _lock:
            _cache[key] = (st.st_mtime, st.st_size, value)
        return value

    return wrapped


def invalidate(path: str | None = None) -> None:
    """Drop one path's entries (any module) or clear everything."""
    with _lock:
        if path is None:
            _cache.clear()
        else:
            stale = [k for k in _cache if k[1] == path]
            for k in stale:
                del _cache[k]


def stats() -> dict:
    """Diagnostic peek — number of cache entries by module."""
    with _lock:
        per_module: dict[str, int] = {}
        for (module, _), _ in _cache.items():
            per_module[module] = per_module.get(module, 0) + 1
        return {"total": len(_cache), "by_module": per_module}
