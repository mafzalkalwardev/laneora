import re
import urllib3
import requests

urllib3.disable_warnings()

r = requests.get("https://193.203.163.61:8443/", timeout=15, verify=False)
print("len", len(r.text), "ctype", r.headers.get("content-type"))
t = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
print("title=", (t.group(1).strip() if t else None))
for m in re.findall(r'href=["\']([^"\']+)["\']', r.text)[:40]:
    print("href", m)
for m in re.findall(r'src=["\']([^"\']+)["\']', r.text)[:20]:
    print("src", m)
print("---")
print(re.sub(r"\s+", " ", r.text)[:2500])

# Soft site headers / robots
for url in (
    "https://soft.awwthat.com/",
    "https://soft.awwthat.com/robots.txt",
    "https://soft.awwthat.com/.env",
    "https://soft.awwthat.com/storage/logs/laravel.log",
    "https://soft.awwthat.com/api",
):
    try:
        rr = requests.get(url, timeout=12)
        print("SOFT", url, rr.status_code, rr.headers.get("content-type"), rr.text[:120].replace("\n", " "))
    except Exception as exc:  # noqa: BLE001
        print("SOFT", url, exc)
