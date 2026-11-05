"""Extract DAT/auth0-looking strings from Chrome Local Storage leveldb files."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LS = Path.home() / "AppData/Local/Google/Chrome/User Data/Profile 1/Local Storage/leveldb"

# Pull printable runs that look like JWT / tokens near DAT markers
PAT = re.compile(
    rb"(one\.dat\.com|power\.dat\.com|login\.dat\.com|auth0|accessToken|id_token|refreshToken|Bearer [A-Za-z0-9\-._~+/]+=*)",
    re.I,
)
JWT = re.compile(rb"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")


def main() -> None:
    hits: list[dict] = []
    for f in sorted(LS.glob("*")):
        if f.suffix not in {".ldb", ".log"} and not f.name.endswith(".log"):
            continue
        try:
            data = f.read_bytes()
        except OSError as exc:
            print("skip", f, exc)
            continue
        for m in PAT.finditer(data):
            start = max(0, m.start() - 80)
            end = min(len(data), m.end() + 120)
            snippet = data[start:end]
            # keep mostly printable
            text = "".join(chr(b) if 32 <= b < 127 else "." for b in snippet)
            hits.append({"file": f.name, "at": m.start(), "text": text})
        for m in JWT.finditer(data):
            # only keep if nearby dat/auth
            window = data[max(0, m.start() - 200) : m.end() + 50]
            if not re.search(rb"dat\.com|auth0|accessToken|id_token", window, re.I):
                continue
            jwt = m.group().decode("ascii", "ignore")
            hits.append({"file": f.name, "at": m.start(), "jwt": jwt[:80] + "...", "len": len(jwt)})

    out = ROOT / "data" / "_p1_localstorage_hits.json"
    out.write_text(json.dumps(hits[:200], indent=2), encoding="utf-8")
    print("hits", len(hits), "wrote", out)
    for h in hits[:40]:
        print(h.get("jwt") or h.get("text", "")[:160])


if __name__ == "__main__":
    main()
