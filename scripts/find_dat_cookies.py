"""Scan local Chrome cookie DBs for dat.com hosts (read-only copy)."""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOTS = [
    Path.home() / "AppData/Local/Google/Chrome/User Data",
    Path.home() / "AppData/Local/Google/Chrome/User",
]

def scan(db: Path) -> list[tuple]:
    tmp = Path(tempfile.mkdtemp()) / "Cookies"
    try:
        shutil.copy2(db, tmp)
        wal = Path(str(db) + "-wal")
        shm = Path(str(db) + "-shm")
        if wal.exists():
            shutil.copy2(wal, Path(str(tmp) + "-wal"))
        if shm.exists():
            shutil.copy2(shm, Path(str(tmp) + "-shm"))
        con = sqlite3.connect(str(tmp))
        cur = con.execute(
            "SELECT host_key, name, path, expires_utc, is_secure, is_httponly "
            "FROM cookies WHERE host_key LIKE '%dat.com%' OR host_key LIKE '%dat.net%' "
            "ORDER BY host_key, name"
        )
        rows = cur.fetchall()
        con.close()
        return rows
    except Exception as exc:  # noqa: BLE001
        return [("ERROR", str(db), str(exc), 0, 0, 0)]
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def main() -> None:
    found = False
    for root in ROOTS:
        if not root.exists():
            continue
        for cookies in root.rglob("Cookies"):
            if "Network" not in str(cookies) and cookies.name != "Cookies":
                continue
            if "Storage" in str(cookies):
                continue
            rows = scan(cookies)
            dat = [r for r in rows if "ERROR" not in r[0] and "dat" in str(r[0]).lower()]
            errs = [r for r in rows if r[0] == "ERROR"]
            if dat or errs:
                found = True
                print("==", cookies)
                for r in (dat or errs)[:40]:
                    print(r)
    if not found:
        print("No DAT cookies found")


if __name__ == "__main__":
    main()
