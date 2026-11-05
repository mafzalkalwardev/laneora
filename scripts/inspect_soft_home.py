import re

import requests

r = requests.get("https://soft.awwthat.com/", timeout=20)
text = r.text
title = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
print("title:", title.group(1).strip() if title else None)
print("hrefs:")
for m in re.findall(r"""href=["']([^"']+)["']""", text)[:50]:
    print(" ", m)
print("actions:")
for m in re.findall(r"""action=["']([^"']+)["']""", text):
    print(" ", m)
plain = re.sub(r"<[^>]+>", " ", text)
plain = re.sub(r"\s+", " ", plain)
print("plain:", plain[:1000])
