"""Stream proxy helpers."""
from __future__ import annotations

from PyQt5.QtNetwork import QNetworkProxy


def apply_http_proxy(host: str, port: int, username: str, password: str) -> QNetworkProxy:
    """Apply app-wide HTTP proxy, or clear proxy for local/direct test mode."""
    host = str(host or "").strip().lower()
    proxy = QNetworkProxy()
    if host in ("", "none", "direct", "local", "0", "false"):
        proxy.setType(QNetworkProxy.NoProxy)
        QNetworkProxy.setApplicationProxy(proxy)
        return proxy
    proxy.setType(QNetworkProxy.HttpProxy)
    proxy.setHostName(str(host))
    proxy.setPort(int(port or 0))
    proxy.setUser(str(username or ""))
    proxy.setPassword(str(password or ""))
    QNetworkProxy.setApplicationProxy(proxy)
    return proxy
