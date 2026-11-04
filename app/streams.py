"""Stream proxy helpers."""
from __future__ import annotations

from PyQt5.QtNetwork import QNetworkProxy


def apply_http_proxy(host: str, port: int, username: str, password: str) -> QNetworkProxy:
    proxy = QNetworkProxy()
    proxy.setType(QNetworkProxy.HttpProxy)
    proxy.setHostName(str(host))
    proxy.setPort(int(port))
    proxy.setUser(str(username))
    proxy.setPassword(str(password))
    QNetworkProxy.setApplicationProxy(proxy)
    return proxy
