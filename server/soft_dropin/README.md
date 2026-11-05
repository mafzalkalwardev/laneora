# Soft `/authenticate` drop-in (CloudPanel)

`soft.awwthat.com` is hosted on **CloudPanel** at `https://193.203.163.61:8443`.  
Laravel’s `/authenticate` currently returns **HTTP 500**. This PHP drop-in implements the Soft client contract so you can replace the broken route on the host.

## Deploy (when you have CloudPanel login)

1. Log into CloudPanel → Soft site → File manager / SSH  
2. Back up the current Soft Laravel app  
3. Point the Soft vhost document root at `public/` from this folder **or** copy `public/index.php` + `users.json` into a working Soft site root with nginx `try_files` → `index.php`  
4. Seed Soft accounts in `users.json`  
5. Verify:

```text
https://soft.awwthat.com/authenticate?username=USER&key=PASSWORD&value=1&is_alive=1
```

Expect JSON with `"status":"okie"` (not HTML 500).

## Local fallback (no CloudPanel needed)

Laneora already auto-starts `server/soft_shim.py` when Soft returns 500:

```powershell
python -m app
```
