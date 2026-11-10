"""Keep one module's DAT login aligned across its search tabs.

Each tab still has its own browser profile, so the search it is running, the
page it is on, and the rest of its storage stay on that tab. Cookies are the
shared login. Auth-token keys in localStorage are copied too, because DAT's
login can refresh those in whichever tab happens to renew them. Other
localStorage keys are not copied.
"""
from __future__ import annotations

import json
import time
from typing import Any

from PyQt5.QtCore import QTimer, QUrl
from PyQt5.QtNetwork import QNetworkCookie

# Keys that carry a login. Search filters and board UI state are left alone.
_AUTH_KEY_JS = r"auth0|access_token|id_token|refresh_token"

TOKEN_SNAPSHOT_JS = f"""
(function() {{
  try {{
    var re = /{_AUTH_KEY_JS}/i;
    var out = {{}};
    for (var i = 0; i < localStorage.length; i++) {{
      var key = localStorage.key(i);
      if (key && re.test(key)) out[key] = localStorage.getItem(key);
    }}
    return JSON.stringify(out);
  }} catch (e) {{
    return "{{}}";
  }}
}})()
"""

# Ignore cookie deletions briefly after open. deleteAllCookies is async and
# would otherwise wipe a login the other tabs just applied.
_REMOVAL_GRACE_SECONDS = 3.0
_ECHO_SECONDS = 1.5


def _qt_object_deleted(obj: object) -> bool:
    try:
        from PyQt5 import sip
    except ImportError:
        return False
    return sip.isdeleted(obj)


def _cookie_key(cookie: QNetworkCookie, *, removed: bool) -> tuple:
    domain = str(cookie.domain() or "").lstrip(".").lower()
    path = str(cookie.path() or "/")
    name = bytes(cookie.name())
    value = b"" if removed else bytes(cookie.value())
    return ("-" if removed else "+", name, domain, path, value)


def _clone_cookie(cookie: QNetworkCookie) -> QNetworkCookie:
    copy = QNetworkCookie(bytes(cookie.name()), bytes(cookie.value()))
    copy.setDomain(str(cookie.domain() or ""))
    copy.setPath(str(cookie.path() or "/"))
    copy.setSecure(bool(cookie.isSecure()))
    copy.setHttpOnly(bool(cookie.isHttpOnly()))
    expires = cookie.expirationDate()
    if expires.isValid():
        copy.setExpirationDate(expires)
    if hasattr(cookie, "sameSitePolicy") and hasattr(copy, "setSameSitePolicy"):
        copy.setSameSitePolicy(cookie.sameSitePolicy())
    return copy


def _cookie_origin(cookie: QNetworkCookie) -> QUrl:
    host = str(cookie.domain() or "").lstrip(".")
    if not host:
        return QUrl()
    scheme = "https" if cookie.isSecure() else "http"
    return QUrl(f"{scheme}://{host}{cookie.path() or '/'}")


def token_write_js(items: dict[str, str]) -> str:
    payload = json.dumps(items)
    return (
        "(function(){ var items = "
        + payload
        + "; try { Object.keys(items).forEach(function(key) {"
        + " localStorage.setItem(key, items[key]); }); } catch (e) {} })()"
    )


def token_remove_js(keys: list[str]) -> str:
    payload = json.dumps(keys)
    return (
        "(function(){ var keys = "
        + payload
        + "; try { keys.forEach(function(key) {"
        + " localStorage.removeItem(key); }); } catch (e) {} })()"
    )


class ProfileSessionSync:
    """Copy login changes from any tab in a module onto the other tabs."""

    def __init__(self) -> None:
        self._pairs: list[tuple[Any, Any]] = []
        self._views: list[Any] = []
        self._opened: set[int] = set()
        self._recent: set[tuple] = set()
        self._known: dict[int, dict[str, str]] = {}
        self._pushed: dict[int, dict[str, str]] = {}
        self._jar: dict[tuple[str, str, str], QNetworkCookie] = {}
        self._closed = False
        self._ignore_removals_until = time.monotonic() + _REMOVAL_GRACE_SECONDS
        self._poll = QTimer()
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self.poll_tokens)
        self._removal_timer = QTimer()
        self._removal_timer.setSingleShot(True)
        self._removal_timer.timeout.connect(self.enable_removals)
        self._removal_timer.start(int(_REMOVAL_GRACE_SECONDS * 1000))

    @property
    def store_count(self) -> int:
        return len(self._pairs)

    @property
    def closed(self) -> bool:
        return self._closed

    def watch(self, profile: Any, view: Any) -> None:
        if self._closed:
            return
        store = profile.cookieStore()
        self._pairs.append((profile, store))
        self._views.append(view)
        profile_id = id(profile)
        store.cookieAdded.connect(lambda cookie, source=profile_id: self._on_cookie_added(source, cookie))
        store.cookieRemoved.connect(lambda cookie, source=profile_id: self._on_cookie_removed(source, cookie))

    def note_opened(self, profile: Any) -> None:
        """The tab has applied its starting session. Later changes are real."""
        self._opened.add(id(profile))

    def enable_removals(self) -> None:
        self._ignore_removals_until = 0.0

    def close(self) -> None:
        self._closed = True
        self._poll.stop()
        self._removal_timer.stop()
        self._poll.deleteLater()
        self._removal_timer.deleteLater()
        self._pairs.clear()
        self._views.clear()

    def start(self) -> None:
        if not self._closed:
            self._poll.start()

    def poll_tokens(self) -> None:
        if self._closed:
            return
        for view in list(self._views):
            if _qt_object_deleted(view):
                continue
            view.page().runJavaScript(
                TOKEN_SNAPSHOT_JS,
                lambda result, source=view: self._on_token_snapshot(source, result),
            )

    def overlay_cookies(self, initial: list[dict]) -> list[dict]:
        """Start from the captured session, then let a later refresh win."""
        merged: dict[tuple[str, str, str], dict] = {}
        for cookie in initial or []:
            key = (
                str(cookie.get("name", "")),
                str(cookie.get("domain", "")).lstrip(".").lower(),
                str(cookie.get("path", "/") or "/"),
            )
            merged[key] = dict(cookie)
        for key, cookie in self._jar.items():
            expires = cookie.expirationDate()
            merged[key] = {
                "name": bytes(cookie.name()).decode("latin1"),
                "value": bytes(cookie.value()).decode("latin1"),
                "domain": str(cookie.domain() or ""),
                "path": str(cookie.path() or "/"),
                "expirationDate": expires.toSecsSinceEpoch() if expires.isValid() else "",
                "httpOnly": bool(cookie.isHttpOnly()),
                "secure": bool(cookie.isSecure()),
            }
        return list(merged.values())

    def _remember(self, key: tuple) -> None:
        self._recent.add(key)
        QTimer.singleShot(int(_ECHO_SECONDS * 1000), lambda key=key: self._recent.discard(key))

    def _on_cookie_added(self, source_id: int, cookie: QNetworkCookie) -> None:
        if self._closed:
            return
        copy = _clone_cookie(cookie)
        identity = (
            bytes(copy.name()).decode("latin1"),
            str(copy.domain() or "").lstrip(".").lower(),
            str(copy.path() or "/"),
        )
        self._jar[identity] = copy
        if source_id not in self._opened:
            return
        key = _cookie_key(copy, removed=False)
        if key in self._recent:
            return
        self._remember(key)
        origin = _cookie_origin(copy)
        for profile, store in list(self._pairs):
            if id(profile) == source_id or id(profile) not in self._opened:
                continue
            store.setCookie(_clone_cookie(copy), origin)

    def _on_cookie_removed(self, source_id: int, cookie: QNetworkCookie) -> None:
        if self._closed or source_id not in self._opened:
            return
        if time.monotonic() < self._ignore_removals_until:
            return
        copy = _clone_cookie(cookie)
        key = _cookie_key(copy, removed=True)
        if key in self._recent:
            return
        self._remember(key)
        for profile, store in list(self._pairs):
            if id(profile) == source_id or id(profile) not in self._opened:
                continue
            store.deleteCookie(_clone_cookie(copy))

    def _on_token_snapshot(self, source: Any, raw: Any) -> None:
        if self._closed or _qt_object_deleted(source):
            return
        try:
            data = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        snapshot = {str(key): "" if value is None else str(value) for key, value in data.items()}
        previous = self._known.get(id(source))
        if previous == snapshot:
            return
        if self._pushed.get(id(source)) == snapshot:
            self._known[id(source)] = snapshot
            self._pushed.pop(id(source), None)
            return
        if previous is None and not snapshot:
            self._known[id(source)] = snapshot
            return
        removed = [key for key in (previous or {}) if key not in snapshot]
        self._known[id(source)] = snapshot
        for view in list(self._views):
            if view is source or _qt_object_deleted(view):
                continue
            if self._known.get(id(view)) == snapshot and not removed:
                continue
            self._pushed[id(view)] = dict(snapshot)
            self._known[id(view)] = dict(snapshot)
            page = view.page()
            if snapshot:
                page.runJavaScript(token_write_js(snapshot))
            if removed:
                page.runJavaScript(token_remove_js(removed))
