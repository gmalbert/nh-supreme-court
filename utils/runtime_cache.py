"""Small cache decorators shared by the Streamlit UI and the FastAPI runtime.

The Streamlit UI delegates to Streamlit's cache implementation. FastAPI opts
into a framework-neutral, bounded, TTL-aware in-process cache even when the UI
package happens to be installed in the same Python environment.
"""

from __future__ import annotations

from collections import OrderedDict
from functools import wraps
import logging
import os
import pickle
from threading import RLock
from time import monotonic
from typing import Any, Callable, TypeVar

if os.environ.get("NHSC_APP_FRAMEWORK", "").lower() == "fastapi":
    _streamlit = None
else:
    try:
        import streamlit as _streamlit
    except ImportError:  # FastAPI runtime does not install the UI framework.
        _streamlit = None

_F = TypeVar("_F", bound=Callable[..., Any])
logger = logging.getLogger(__name__)


def _fallback_cache(*, ttl: float | None, resource: bool, max_entries: int = 128):
    def decorate(function: _F) -> _F:
        values: OrderedDict[bytes, tuple[float, Any]] = OrderedDict()
        lock = RLock()

        @wraps(function)
        def cached(*args: Any, **kwargs: Any) -> Any:
            try:
                key = pickle.dumps((args, sorted(kwargs.items())), protocol=pickle.HIGHEST_PROTOCOL)
            except (pickle.PickleError, TypeError, ValueError):
                return function(*args, **kwargs)

            now = monotonic()
            with lock:
                entry = values.get(key)
                if entry and (ttl is None or now - entry[0] < ttl):
                    values.move_to_end(key)
                    value = entry[1]
                    return value if resource else pickle.loads(value)
                if entry:
                    del values[key]

            result = function(*args, **kwargs)
            try:
                stored = result if resource else pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
            except (pickle.PickleError, TypeError, ValueError):
                logger.debug("Skipping cache for non-serializable result from %s", function.__qualname__)
                return result
            with lock:
                values[key] = (monotonic(), stored)
                values.move_to_end(key)
                while len(values) > max_entries:
                    values.popitem(last=False)
            return result if resource else pickle.loads(stored)

        def clear() -> None:
            with lock:
                values.clear()

        cached.clear = clear  # type: ignore[attr-defined]
        return cached  # type: ignore[return-value]

    return decorate


def cache_data(function: _F | None = None, *, ttl: float | None = None, **options: Any):
    """Cache data results, returning independent copies where serializable."""
    if _streamlit is not None:
        decorator = _streamlit.cache_data(ttl=ttl, **options)
    else:
        decorator = _fallback_cache(ttl=ttl, resource=False)
    return decorator(function) if function is not None else decorator


def cache_resource(function: _F | None = None, **options: Any):
    """Cache one shared resource instance for each argument set."""
    if _streamlit is not None:
        decorator = _streamlit.cache_resource(**options)
    else:
        decorator = _fallback_cache(ttl=None, resource=True)
    return decorator(function) if function is not None else decorator


def streamlit_secret(name: str) -> Any:
    """Read a legacy Streamlit secret when that framework is installed."""
    if _streamlit is None:
        return None
    try:
        return _streamlit.secrets.get(name)
    except Exception:
        return None
