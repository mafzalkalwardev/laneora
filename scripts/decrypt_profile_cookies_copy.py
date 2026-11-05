"""Decrypt a copied Chrome Cookies DB into data/dat_cookies_captured.json."""
from __future__ import annotations

import base64
import json
import sqlite3
import sys
from pathlib import Path

import win32crypt
from Crypto.Cipher import AES

ROOT = Path(__file__).resolve().parents[1]
USER_DATA = Path.home() / "AppData/Local/Google/Chrome/User Data"


def chrome_key() -> bytes:
    local_state = json.loads((USER_DATA / "Local State").read_text(encoding="utf-8"))
    enc = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    if enc[:5] != b"DPAPI":
        raise RuntimeError("unexpected encrypted_key prefix")
    return win32crypt.CryptUnprotectData(enc[5:], None, None, None, 0)[1]


def decrypt_value(key: bytes, blob: bytes) -> str:
    if not blob:
        return ""
    if blob[:3] in (b"v10", b"v11"):
        nonce = blob[3:15]
        ciphertext = blob[15:-16]
        tag = blob[-16:]
        return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ciphertext, tag).decode(
            "utf-8", errors="replace"
        )
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8", errors="replace")


def main() -> int:
    db = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "_p1_cookies")
    profile = sys.argv[2] if len(sys.argv) > 2 else "Profile 1"
    key = chrome_key()
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT host_key, name, value, encrypted_value, path, expires_utc, "
        "is_secure, is_httponly FROM cookies "
        "WHERE host_key LIKE '%dat.com%' OR host_key LIKE '%dat.net%' "
        "ORDER BY host_key, name"
    ).fetchall()
    con.close()
    print("rows", len(rows))

    store = []
    fails = 0
    for host, name, value, encv, path, expires, secure, httponly in rows:
        plain = value or ""
        if not plain and encv:
            try:
                plain = decrypt_value(key, encv)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                if fails <= 8:
                    print("fail", host, name, type(exc).__name__, exc)
                continue
        if not plain:
            continue
        item = {
            "name": name,
            "value": plain,
            "domain": host,
            "path": path or "/",
            "secure": bool(secure),
            "httpOnly": bool(httponly),
        }
        if expires and expires > 0:
            item["expirationDate"] = (expires / 1_000_000) - 11644473600
        store.append(item)

    print("store", len(store), "fails", fails)
    print("names", sorted({c["name"] for c in store}))
    for need in ("auth0", "did", "cf_clearance", "auth0_compat"):
        hits = [c for c in store if c["name"] == need]
        print(need, [(len(c["value"]), c["domain"]) for c in hits])

    out = ROOT / "data" / "dat_cookies_captured.json"
    out.write_text(
        json.dumps(
            {
                "url": "https://one.dat.com",
                "lst": "{}",
                "sst": "",
                "source_profile": profile,
                "source": "live-db-no-restart",
                "store": store,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", out)
    return 0 if store else 1


if __name__ == "__main__":
    raise SystemExit(main())
