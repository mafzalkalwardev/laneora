"""Pure decisions for the embedded DAT view. No Qt."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def is_blank_url(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return True
    parsed = urlparse(text)
    return parsed.scheme in {"", "about"} or text.lower().startswith("about:")


def cookie_origin(domain: str) -> str:
    """Origin passed to QWebEngineCookieStore.setCookie. An empty URL drops the cookie."""
    host = str(domain or "").strip()
    if host.startswith("."):
        host = host[1:]
    if not host:
        host = "one.dat.com"
    return f"https://{host}/"


def on_load_event(url: str, ok: bool, committed: bool) -> str:
    """about:blank is the view's first document. It must not count as DAT or be reloaded."""
    if committed or is_blank_url(url):
        return "ignore"
    if ok:
        return "inject"
    return "fail"


def describe_navigation(url: str, proxy_host: str, store: list[Any] | None, *, ok: bool | None = None) -> str:
    cookies = [cookie for cookie in (store or []) if isinstance(cookie, dict)]
    names = {str(cookie.get("name") or "") for cookie in cookies}
    auth = "present" if "auth0" in names else "missing"
    host = str(proxy_host or "").strip().lower()
    if host in {"", "none", "direct", "local", "0", "false"}:
        host = "direct"
    result = "pending" if ok is None else ("ok" if ok else "fail")
    return f"result={result} url={url} proxy={host} cookies={len(cookies)} auth0={auth}"
