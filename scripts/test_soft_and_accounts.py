"""
Test Soft.awwthat.com health + multi-account Soft-compatible auth with DAT payloads.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import PASSPHRASE  # noqa: E402
from app.crypto_util import decrypt  # noqa: E402
from app.roster import save_roster, upsert_user  # noqa: E402

SOFT = "https://soft.awwthat.com"
LOCAL = "http://127.0.0.1:8787"


def check_soft() -> dict:
    out = {}
    for path in ("/latest_version", "/linetext", "/authenticate", "/logger"):
        params = {
            "username": "mafzalk",
            "key": "mafzalk",
            "value": "1",
            "is_alive": "1",
            "uva": "mafzalk:1:1",
        }
        try:
            r = requests.get(
                SOFT + path,
                params=params,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            out[path] = {"status": r.status_code, "body": r.text[:160]}
        except Exception as exc:  # noqa: BLE001
            out[path] = {"error": str(exc)}
    return out


def sync_roster_from_local() -> None:
    local = json.loads((ROOT / "data" / "local_users.json").read_text(encoding="utf-8"))
    save_roster([])
    for user in local.get("users") or []:
        upsert_user(str(user["username"]), str(user["password"]), str(user["username"]))


def wait_local(timeout: float = 15.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(LOCAL + "/latest_version", timeout=2)
            if r.status_code == 200:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.4)
    raise RuntimeError("local API did not start")


def test_account(base: str, username: str, password: str) -> dict:
    r = requests.get(
        base + "/authenticate",
        params={
            "username": username,
            "key": password,
            "value": "4242",
            "is_alive": "7",
        },
        headers={"Accept": "application/json"},
        timeout=30,
    )
    result: dict = {"username": username, "http": r.status_code, "ok": False}
    if r.status_code != 200:
        result["body"] = r.text[:200]
        return result
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        result["body"] = r.text[:200]
        return result
    if not isinstance(data, dict) or data.get("status") != "okie":
        result["body"] = data
        return result
    streams = [s for s in str(data.get("active_subs") or "").split(",") if s]
    decoded = {}
    for name in streams:
        plain = json.loads(decrypt(PASSPHRASE, data[name]))
        decoded[name] = plain.get("url")
    result["ok"] = True
    result["streams"] = decoded
    result["proxy"] = {"px": data.get("px"), "p": data.get("p")}
    lg = requests.get(base + "/logger", params={"uva": f"{username}:4242:7"}, timeout=15)
    result["logger"] = lg.text
    # DAT reachability (public pages)
    for url in decoded.values():
        try:
            head = requests.get(str(url), timeout=20, allow_redirects=True)
            result.setdefault("dat_http", {})[str(url)] = head.status_code
        except Exception as exc:  # noqa: BLE001
            result.setdefault("dat_http", {})[str(url)] = str(exc)
    return result


def main() -> int:
    print("=== Soft.awwthat.com health ===")
    soft = check_soft()
    for path, info in soft.items():
        print(path, info)
    soft_auth = soft.get("/authenticate", {})
    soft_ok = soft_auth.get("status") == 200 and "okie" in str(soft_auth.get("body", ""))

    print("\n=== Sync Soft roster + local Soft-compatible multi-account DAT test ===")
    sync_roster_from_local()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "server" / "local_api.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_local()
        accounts = [
            ("admin", "admin123"),
            ("mafzalk", "mafzalk"),
            ("dispatcher2", "dispatch123"),
        ]
        all_ok = True
        for user, pw in accounts:
            # Soft first
            soft_res = test_account(SOFT, user, pw)
            print("SOFT", soft_res)
            # Local Soft-compatible
            local_res = test_account(LOCAL, user, pw)
            print("LOCAL", local_res)
            if not local_res.get("ok"):
                all_ok = False
            else:
                for url in (local_res.get("streams") or {}).values():
                    if "dat.com" not in str(url):
                        all_ok = False
        print("\nSOFT_AUTH_WORKING=", soft_ok)
        print("LOCAL_MULTI_ACCOUNT_DAT_OK=", all_ok)
        return 0 if all_ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
