"""WebEngine helpers: UA, modal remover, cookies, localStorage."""
from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QDateTime, Qt, QUrl
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineScript, QWebEngineView

from app import USER_AGENT

CHECKER_SCRIPT = """
                function remover() {
                    var ob1 = document.getElementsByClassName('ui-dialog ui-widget ui-widget-content ui-corner-all ui-front usurpModal')[0];
                    var ob2 = document.getElementsByClassName('ui-widget-overlay ui-front')[0];
                    var ob3 = document.getElementsByClassName('cdk-overlay-backdrop cdk-overlay-dark-backdrop cdk-overlay-backdrop-showing')[0];
                    var ob4 = document.getElementsByClassName('mat-dialog-container ng-tns-c45-0 ng-trigger ng-trigger-dialogContainer ng-star-inserted')[0];
                    var ob5 = document.getElementsByClassName('mat-dialog-container ng-tns-c42-9 ng-trigger ng-trigger-dialogContainer ng-star-inserted')[0];
                    var ob6 = document.getElementsByClassName('mat-dialog-container ng-tns-c42-36 ng-trigger ng-trigger-dialogContainer ng-star-inserted')[0];
                    var ob7 = document.getElementsByClassName('cdk-overlay-backdrop cdk-overlay-dark-backdrop cdk-overlay-backdrop-showing')[0];
                    var ob8 = document.getElementsByClassName('mat-dialog-container ng-trigger ng-trigger-dialogContainer ng-star-inserted')[0];
                    var ob9 = document.getElementsByClassName('nav-links')[0];
                    var ob10 = document.getElementsByTagName('dat-worklist-controls')[0];

                    [...document.querySelectorAll('*')].forEach(el => {
                        if (el.textContent.trim().toLowerCase() === 'book') {
                            el.remove();
                        }
                    });

                    [...document.querySelectorAll('*')].forEach(el => {
                        if (el.textContent.trim().toLowerCase() === 'book load') {
                            el.remove();
                        }
                    });

                    [...document.querySelectorAll('*')].forEach(el => {
                        if (el.textContent.trim().toLowerCase() === 'prefer') {
                            el.remove();
                        }
                    });

                    [...document.querySelectorAll('*')].forEach(el => {
                        if (el.textContent.trim().toLowerCase() === 'block') {
                            el.remove();
                        }
                    });


                    if (ob1) {
                        ob1.remove();
                    }
                    if (ob2) {
                        ob2.remove();
                    }
                    if (ob3) {
                        ob3.remove();
                    }
                    if (ob4) {
                        ob4.remove();
                    }
                    if (ob5) {
                        ob5.remove();
                    }
                    if (ob6) {
                        ob6.remove();
                    }
                    if (ob7) {
                        ob7.remove();
                    }
                    if (ob8) {
                        ob8.remove();
                    }
                    if (ob9) {
                        ob9.remove();
                    }
                    if (ob10) {
                        ob10.remove();
                    }
                }
                setInterval(remover, 100);
                """


def attach_checker_script(view: QWebEngineView) -> None:
    script = QWebEngineScript()
    script.setSourceCode(CHECKER_SCRIPT)
    script.setInjectionPoint(QWebEngineScript.DocumentReady)
    view.page().profile().scripts().insert(script)
    view.page().profile().setHttpUserAgent(USER_AGENT)


def apply_cookies(cookie_store, store: list[dict[str, Any]]) -> None:
    for cookie in store or []:
        qcookie = QNetworkCookie()
        qcookie.setName(str(cookie.get("name", "")).encode())
        qcookie.setValue(str(cookie.get("value", "")).encode())
        qcookie.setDomain(str(cookie.get("domain", "")))
        qcookie.setPath(str(cookie.get("path", "")))
        expiration_date_str = str(cookie.get("expirationDate", "") or "")
        if expiration_date_str:
            expiration_date = QDateTime.fromString(expiration_date_str, Qt.ISODate)
            qcookie.setExpirationDate(expiration_date)
        qcookie.setHttpOnly(bool(cookie.get("httpOnly", False)))
        qcookie.setSecure(bool(cookie.get("secure", False)))
        cookie_store.setCookie(qcookie, QUrl())


def inject_local_storage(view: QWebEngineView, loc_str: str) -> None:
    scripto = (
        "\n        var jso = "
        f"{loc_str}"
        ";\n        var items = JSON.parse(jso);\n"
        "        for (var key in items) {\n"
        "            localStorage.setItem(key, items[key]);\n"
        "        }\n        "
    )
    view.page().runJavaScript(scripto)


def clear_profile(profile: QWebEngineProfile) -> None:
    profile.clearAllVisitedLinks()
    profile.clearHttpCache()
