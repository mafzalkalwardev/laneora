import re
import requests

r = requests.get("https://soft.awwthat.com/", timeout=30)
print("len", len(r.text))
for m in re.findall(r'href=["\']([^"\']+)["\']', r.text)[:50]:
    print("href", m)
for m in re.findall(r'src=["\']([^"\']+)["\']', r.text)[:30]:
    print("src", m)
print("---")
print(re.sub(r"\s+", " ", r.text)[:2000])
