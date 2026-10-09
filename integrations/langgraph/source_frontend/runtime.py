"""Offline pure request helpers used by whitelisted source fixtures.

Source authored for the frontend imports ``request`` and ``tokens`` and calls
them only inside LangGraph node/router functions. A probe binds one
``OfflineRequestSession`` around ``app.invoke``; outside that scope the helpers
fail closed. This module does not connect to a provider.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Iterator


_SESSION: ContextVar[Any | None] = ContextVar("orchlang_source_request_session", default=None)


@contextmanager
def bind_session(session: Any) -> Iterator[None]:
    """Bind a single offline session for one synchronous LangGraph invoke."""
    if not callable(getattr(session, "request", None)) or not callable(getattr(session, "tokens", None)):
        raise TypeError("session must provide request() and tokens()")
    token: Token[Any | None] = _SESSION.set(session)
    try:
        yield
    finally:
        _SESSION.reset(token)


def _bound_session() -> Any:
    session = _SESSION.get()
    if session is None:
        raise RuntimeError("source request helper used outside an offline probe session")
    return session


def request(*, model: str, template: str, arguments: list[str]) -> str:
    """Issue one request through the currently bound offline Ω session."""
    return _bound_session().request(model, template, arguments)


def tokens(text: str) -> int:
    """Return UTF-8 byte-divisor units for the current offline session."""
    return _bound_session().tokens(text)
