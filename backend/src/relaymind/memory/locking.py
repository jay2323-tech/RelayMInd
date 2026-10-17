"""Shared serialization within one Python process; not a distributed lock."""
from functools import wraps
from threading import RLock

_MEMORY_WRITE_LOCK = RLock()


def serialized_write(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _MEMORY_WRITE_LOCK:
            return fn(*args, **kwargs)
    return wrapped
