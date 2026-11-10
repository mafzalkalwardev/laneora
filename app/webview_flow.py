"""Decisions for the embedded DAT view that do not need Qt.

An empty cookie origin and deleteAllCookies were wiping the session on some
machines and leaving the view on about:blank.
"""
from __future__ import annotations

from urllib.parse import urlparse


def is_blank_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return True
    parsed = urlparse(text)
    return parsed.scheme in {"", "about"} or text.lower().startswith("about:")


def cookie_origin(domain: str) -> str:
    """Origin for QWebEngineCookieStore.setCookie. An empty URL drops the cookie."""
    host = str(domain or "").strip()
    if host.startswith("."):
        host = host[1:]
    if not host:
        host = "one.dat.com"
    return f"https://{host}/"


def on_load_event(url: str, ok: bool, committed: bool) -> str:
    """about:blank is the view's first document. It is not a loaded DAT page."""
    if committed or (ok and is_blank_url(url)):
        return "ignore"
    if ok:
        return "inject"
    return "fail"
