# Recovery notes from Awwthat Pro v2.3 (`appv2.3`)

Evidence: `_reference/Awwthat Pro v2.3.exe` → PyInstaller entry `sappv2.3`, disassembly in `appv2.3.dis.txt`.

## Constants
- `server_url` = `https://soft.awwthat.com`
- `pp` (AES passphrase) = `raw_value`
- `usag` = Chrome 122 desktop UA
- `version` = `2.3` (Laneora ships as `3.0.0`)
- `checker_script` = interval remover for DAT usurpModal / book / prefer / block UI

## Auth
`GET {server_url}/authenticate?username=&key=&value=&is_alive=`
- username/password lowercased + whitespace stripped
- `value` / `is_alive` random ints
- success when JSON `status == "okie"` (failure when body parses as `0`)
- fields: `p`, `active_subs` (comma streams), `px`, `pu`, `pd`, plus per-stream encrypted blobs keyed by stream name

## Logger heartbeat
Background loop: `GET {server_url}/logger?uva={username}:{value}:{is_alive}`
- response text must equal `str(value)` or show “Multiple Screens not allowed” / exit

## Stream browse
- Decrypt stream blob with `decrypt(pp, blob)` → JSON `{url, store, lst, sst}`
- Apply `QNetworkProxy.HttpProxy(px, int(p), pu, pd)`
- If `"power" in opt` force `https://power.dat.com`
- Inject cookies from `store`; localStorage from `lst`

## Updates
- `GET /latest_version` vs local version
- `GET /update` streamed to `{Brand} v{ver}.exe`
