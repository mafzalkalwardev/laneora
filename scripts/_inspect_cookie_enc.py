import json
import sqlite3
from collections import Counter
from pathlib import Path

con = sqlite3.connect(r"d:\Dispatch Softwares\Laneora\data\_p1_cookies")
rows = con.execute(
    "SELECT host_key, name, encrypted_value, length(encrypted_value) FROM cookies "
    "WHERE host_key LIKE '%dat.com%'"
).fetchall()
prefs: Counter[bytes] = Counter()
for host, name, blob, length in rows:
    pref = bytes(blob[:5]) if blob else b""
    print(host, name, pref, "len", length)
    prefs[bytes(blob[:3]) if blob else b""] += 1
print("prefixes", prefs)

ls = json.loads(
    (Path.home() / "AppData/Local/Google/Chrome/User Data/Local State").read_text(encoding="utf-8")
)
oc = ls.get("os_crypt", {})
print("os_crypt keys", list(oc.keys()))
for k, v in oc.items():
    if isinstance(v, str):
        print(k, (v[:60] + "...") if len(v) > 60 else v)
    else:
        print(k, type(v).__name__, v)
