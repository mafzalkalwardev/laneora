"""Capture DAT cookies from a live Chrome profile DB (no Chrome restart / no CDP).

Copies Network/Cookies (+ WAL) from the given profile, decrypts with Windows DPAPI
+ Chrome AES-GCM key from Local State, writes data/dat_cookies_captured.json.
"""
from __future__ import annotations

import base64
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import win32crypt
from Crypto.Cipher import AES

ROOT = Path(__file__).resolve().parents[1]
USER_DATA = Path.home() / "AppData/Local/Google/Chrome/User Data"


def chrome_key(user_data: Path) -> bytes:
    local_state = json.loads((user_data / "Local State").read_text(encoding="utf-8"))
    enc = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    assert enc[:5] == b"DPAPI", "unexpected encrypted_key prefix"
    return win32crypt.CryptUnprotectData(enc[5:], None, None, None, 0)[1]


def decrypt_value(key: bytes, blob: bytes) -> str:
    if not blob:
        return ""
    # Chrome v80+: v10 / v11 + nonce(12) + ciphertext + tag(16)
    if blob[:3] in (b"v10", b"v11"):
        nonce = blob[3:15]
        ciphertext = blob[15:-16]
        tag = blob[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8", errors="replace")
    # Legacy DPAPI
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode(
        "utf-8", errors="replace"
    )


def chrome_expiry_to_unix(expires_utc: int) -> float | None:
    # Chrome: microseconds since 1601-01-01
    if not expires_utc or expires_utc <= 0:
        return None
    return (expires_utc / 1_000_000) - 11644473600


def copy_cookie_db(src: Path, dest_dir: Path) -> Path:
    dest = dest_dir / "Cookies"
    shutil.copy2(src, dest)
    for suffix in ("-wal", "-shm"):
        side = Path(str(src) + suffix)
        if side.exists():
            shutil.copy2(side, Path(str(dest) + suffix))
    return dest


def capture(profile: str) -> int:
    profile_dir = USER_DATA / profile
    cookies_path = profile_dir / "Network" / "Cookies"
    if not cookies_path.exists():
        print("missing", cookies_path)
        return 1

    key = chrome_key(USER_DATA)
    tmp = Path(tempfile.mkdtemp(prefix="dat_cookies_"))
    try:
        db = copy_cookie_db(cookies_path, tmp)
        con = sqlite3.connect(str(db))
        rows = con.execute(
            "SELECT host_key, name, value, encrypted_value, path, expires_utc, "
            "is_secure, is_httponly FROM cookies "
            "WHERE host_key LIKE '%dat.com%' OR host_key LIKE '%dat.net%' "
            "ORDER BY host_key, name"
        ).fetchall()
        con.close()

        store = []
        for host, name, value, enc, path, expires, secure, httponly in rows:
            plain = value or ""
            if not plain and enc:
                try:
                    plain = decrypt_value(key, enc)
                except Exception as exc:  # noqa: BLE001
                    print(f"decrypt fail {host} {name}: {exc}")
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
            exp = chrome_expiry_to_unix(expires)
            if exp is not None:
                item["expirationDate"] = exp
            store.append(item)

        out = ROOT / "data" / "dat_cookies_captured.json"
        out.write_text(
            json.dumps(
                {
                    "url": "https://one.dat.com",
                    "lst": "{}",
                    "sst": "",
                    "source_profile": profile,
                    "store": store,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        names = sorted({c["name"] for c in store})
        print(f"profile={profile} dat_cookies={len(store)}")
        print("names", names)
        print("wrote", out)
        authish = [n for n in names if any(x in n.lower() for x in ("auth", "token", "session", "jwt", "sid", "access"))]
        print("authish", authish)
        return 0 if store else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    prof = sys.argv[1] if len(sys.argv) > 1 else "Profile 410"
    raise SystemExit(capture(prof))
