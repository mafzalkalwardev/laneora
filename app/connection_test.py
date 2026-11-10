"""Reachability, latency, and a short download sample. No extra packages."""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

DAT_URLS = (
    "https://one.dat.com/",
    "https://login.dat.com/",
    "https://www.dat.com/",
)
_SAMPLE_BYTES = 256_000
_TIMEOUT = 8.0


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    group: str


def _host(url: str) -> str:
    return urlparse(url).netloc or url


def proxy_dict(
    host: str,
    port: int | str,
    username: str = "",
    password: str = "",
) -> dict[str, str] | None:
    cleaned = str(host or "").strip()
    if cleaned.lower() in ("", "none", "direct", "local", "0", "false"):
        return None
    auth = ""
    if username:
        auth = f"{username}:{password}@"
    proxy = f"http://{auth}{cleaned}:{int(port or 0)}"
    return {"http": proxy, "https": proxy}


def check_url(
    url: str,
    *,
    proxies: dict[str, str] | None = None,
    timeout: float = _TIMEOUT,
) -> Check:
    """Time to first byte, then read at most a small sample. The detail has no secrets."""
    started = time.perf_counter()
    group = "proxy" if proxies else "direct"
    try:
        response = requests.get(
            url,
            timeout=timeout,
            proxies=proxies,
            stream=True,
            allow_redirects=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        total = 0
        for chunk in response.iter_content(16_384):
            if not chunk:
                continue
            total += len(chunk)
            if total >= _SAMPLE_BYTES:
                break
        response.close()
        elapsed = max(time.perf_counter() - started, 0.001)
        kbps = (total / 1024) / elapsed
        detail = (
            f"HTTP {response.status_code}, first byte {latency_ms:.0f} ms, "
            f"sample {total / 1024:.0f} KB at {kbps:.0f} KB/s"
        )
        return Check(_host(url), 200 <= response.status_code < 500, detail, group)
    except requests.RequestException as exc:
        return Check(_host(url), False, f"no answer ({type(exc).__name__})", group)


def run_checks(
    *,
    proxy_host: str = "",
    proxy_port: int | str = 0,
    proxy_user: str = "",
    proxy_password: str = "",
    urls: tuple[str, ...] = DAT_URLS,
    timeout: float = _TIMEOUT,
) -> list[Check]:
    proxies = proxy_dict(proxy_host, proxy_port, proxy_user, proxy_password)
    checks = [check_url(url, timeout=timeout) for url in urls]
    if proxies is not None:
        checks.append(Check("proxy", True, f"configured host {str(proxy_host).strip()}", "info"))
        checks.extend(check_url(url, proxies=proxies, timeout=timeout) for url in urls)
    else:
        checks.append(Check("proxy", True, "not configured; this PC connects directly", "info"))
    return checks


def advice(checks: list[Check]) -> str:
    direct = [item for item in checks if item.group == "direct"]
    proxied = [item for item in checks if item.group == "proxy"]
    direct_ok = any(item.ok for item in direct)
    proxy_ok = any(item.ok for item in proxied)
    if proxied and direct_ok and not proxy_ok:
        return (
            "This PC can reach DAT directly, but not through the proxy. "
            "A white page is likely the proxy. Ask the admin to check the proxy host and port."
        )
    if direct and not direct_ok:
        return (
            "This PC cannot reach DAT. Check Wi-Fi, the firewall, and any VPN. "
            "A white page here is the network, not a board login."
        )
    if proxied and proxy_ok and direct_ok:
        return (
            "DAT and the proxy answered. If the page is still white, the graphics driver is the likely cause. "
            "Close Laneora and open it again with lightweight mode."
        )
    if direct_ok and not proxied:
        return (
            "DAT answered and no proxy is set. If the page is still white, "
            "close Laneora and open it again with lightweight mode so it skips GPU rendering."
        )
    return "Some DAT checks failed. Retry after the network is steady, or send the log file."


def format_report(checks: list[Check]) -> str:
    lines = []
    for item in checks:
        mark = "PASS" if item.ok else "FAIL"
        if item.group == "proxy":
            mark = f"{mark} via proxy"
        elif item.group == "info":
            mark = "INFO"
        lines.append(f"{mark}  {item.name} — {item.detail}")
    lines.append("")
    lines.append(advice(checks))
    return "\n".join(lines)
