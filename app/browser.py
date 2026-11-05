"""WebEngine helpers: UA, modal remover, cookies, localStorage."""
from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QDateTime, Qt, QUrl
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineScript, QWebEngineView

from app import USER_AGENT

# Proven on the shared DAT session: hide the side menu (Search Loads only)
# and remove DAT's "logged in on another device" dialog. Do not click Login Anyway.
CHECKER_SCRIPT = """
                function remover() {
                    if (!document.getElementById('laneora-soft-hide')) {
                        var css = document.createElement('style');
                        css.id = 'laneora-soft-hide';
                        css.textContent = [
                            '.nav-links,dat-worklist-controls,dat-certificate-of-insurance-banner,.certificate-banner-container,',
                            'connected-email-connect-cta,connected-email-connect-button,connected-email-connect-modal,',
                            'dat-load-details .mat-icon:empty,dat-load-details mat-icon:empty,',
                            '.expanded-detail-row .mat-icon:empty,.expanded-detail-row mat-icon:empty,',
                            '.table-row-detail .mat-icon:empty,.details-container .mat-icon:empty,',
                            'dat-load-details img[src=""],dat-load-details img:not([src]),',
                            '.origin-destination mat-icon,.route-arrow,.trip-arrow',
                            '{display:none!important;width:0!important;height:0!important;overflow:hidden!important;}'
                        ].join('');
                        (document.head || document.documentElement).appendChild(css);
                    }
                    if (location.hostname === 'one.dat.com') {
                        var path = location.pathname || '/';
                        var other = /\\/(dashboard|company|my-company|my-trucks|my-loads|private-network|tools|notifications|my-account|support)(\\/|$)/i;
                        if (path.indexOf('/search-loads') !== 0 && other.test(path)) {
                            var now = Date.now();
                            if (!window.__laneoraHop || now - window.__laneoraHop > 8000) {
                                window.__laneoraHop = now;
                                location.replace('https://one.dat.com/search-loads');
                                return;
                            }
                        }
                    }
                    document.querySelectorAll(
                        '.nav-links, dat-worklist-controls, dat-certificate-of-insurance-banner, .certificate-banner-container, connected-email-connect-cta, connected-email-connect-button, connected-email-connect-modal'
                    ).forEach(function (el) {
                        el.remove();
                    });
                    document.querySelectorAll('a, button').forEach(function (el) {
                        var t = (el.textContent || '').trim().toLowerCase();
                        if (t === 'book' || t === 'book load' || t === 'prefer' || t === 'block' || t === 'connect email' || t === 'sign in with microsoft' || t === 'sign in with google') {
                            el.remove();
                        }
                    });
                    var oops = /logged in on another device|login anyway/i;
                    document.querySelectorAll(
                        '.usurpModal, .ui-widget-overlay, .cdk-overlay-backdrop, .cdk-overlay-pane, .mat-dialog-container'
                    ).forEach(function (el) {
                        var t = el.innerText || '';
                        if (
                            oops.test(t) ||
                            el.classList.contains('cdk-overlay-backdrop') ||
                            el.classList.contains('usurpModal') ||
                            el.classList.contains('ui-widget-overlay')
                        ) {
                            el.remove();
                        }
                    });
                }
                setInterval(remover, 150);
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
        raw_exp = cookie.get("expirationDate", "") or ""
        if isinstance(raw_exp, (int, float)) or (
            isinstance(raw_exp, str) and raw_exp.replace(".", "", 1).isdigit()
        ):
            secs = int(float(raw_exp))
            if secs > 10_000_000_000:
                secs //= 1000
            if secs > 0:
                qcookie.setExpirationDate(QDateTime.fromSecsSinceEpoch(secs))
        else:
            expiration_date = QDateTime.fromString(str(raw_exp), Qt.ISODate)
            if expiration_date.isValid():
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
