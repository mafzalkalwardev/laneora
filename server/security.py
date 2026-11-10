"""Password hashing, revocable admin sessions, CSRF, throttling, and TOTP.

Stdlib only. Dashboard passwords are case-sensitive. Client passwords are hashed
after the same fold the desktop client already applies before it sends them, so
existing dispatcher binaries keep working without a plaintext compare.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import urlparse

DEFAULT_PBKDF2_ITERATIONS = 600_000
PBKDF2_ITERATIONS = DEFAULT_PBKDF2_ITERATIONS
SESSION_TTL_SECONDS = 12 * 3600
ADMIN_LOGIN_LIMIT = 8
ADMIN_LOGIN_WINDOW = 15 * 60
CLIENT_AUTH_LIMIT = 40
CLIENT_AUTH_WINDOW = 15 * 60

# Published dashboard seeds and other passwords that must never be stored.
KNOWN_DASHBOARD_DEFAULTS = frozenset(
    {
        "admin",
        "admin123",
        "password",
        "laneora",
        "changeme",
    }
)

_WS_RE = re.compile(r"^[\s\u200B\u00A0]+|[\s\u200B\u00A0]+$")
_SECRET_QUERY = re.compile(
    r"(?i)([?&\s]|^)(key|password|passwd|pwd|pd|pu|secret|code|token)=([^&\s\"']*)"
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_dummy_hash: str | None = None
_throttle_lock = threading.Lock()
_admin_hits: dict[str, list[float]] = {}
_client_hits: dict[str, list[float]] = {}


def normalize_client_secret(value: str) -> str:
    """Match app.auth.normalize_credential: trim, lowercase, drop edge zero-width spaces."""
    value = str(value or "").strip().lower()
    return _WS_RE.sub("", value)


def is_password_hash(value: str) -> bool:
    parts = str(value or "").split("$")
    return len(parts) == 4 and parts[0] == "pbkdf2_sha256" and parts[1].isdigit() and int(parts[1]) > 0


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(password: str, *, iterations: int | None = None) -> str:
    rounds = int(iterations or PBKDF2_ITERATIONS)
    if rounds < 1:
        raise ValueError("Invalid password hash cost.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds_text, salt_text, digest_text = str(encoded or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_text)
        if rounds < 1 or rounds > 5_000_000:
            return False
        salt = _b64d(salt_text)
        expected = _b64d(digest_text)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def dummy_password_hash() -> str:
    global _dummy_hash
    prefix = f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
    if _dummy_hash is None or not _dummy_hash.startswith(prefix):
        _dummy_hash = hash_password("not-a-real-password")
    return _dummy_hash


def hash_client_password(password: str) -> str:
    normalized = normalize_client_secret(password)
    if not normalized:
        raise ValueError("Password must not be empty.")
    return hash_password(normalized)


def verify_client_password(presented: str, stored_hash: str) -> bool:
    normalized = normalize_client_secret(presented)
    if not normalized or not is_password_hash(stored_hash):
        verify_password(normalized or "missing", dummy_password_hash())
        return False
    return verify_password(normalized, stored_hash)


def validate_dashboard_username(username: str) -> str:
    username = str(username or "").strip()
    if not 8 <= len(username) <= 64:
        raise ValueError("Dashboard username must be 8–64 characters.")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(ch not in allowed for ch in username):
        raise ValueError("Dashboard username can use letters, numbers, _ and - only.")
    if username.lower() == "admin":
        raise ValueError("Choose a dashboard username that is not admin.")
    return username


def validate_dashboard_password(password: str, username: str) -> str:
    password = str(password or "").strip()
    if len(password) < 12:
        raise ValueError("Dashboard password must be at least 12 characters.")
    if len(password) > 200:
        raise ValueError("Dashboard password is too long.")
    folded = password.lower()
    if folded in KNOWN_DASHBOARD_DEFAULTS or password in KNOWN_DASHBOARD_DEFAULTS:
        raise ValueError("That dashboard password is not allowed.")
    if folded == str(username or "").strip().lower():
        raise ValueError("Dashboard password must not match the username.")
    return password


def valid_session_key(value: str) -> bool:
    try:
        raw = bytes.fromhex(str(value or ""))
    except ValueError:
        return False
    return len(raw) == 32


def new_session_key() -> str:
    return secrets.token_hex(32)


def _dashboard(cfg: dict[str, Any]) -> dict[str, Any]:
    dash = cfg.get("dashboard")
    if not isinstance(dash, dict):
        dash = {}
        cfg["dashboard"] = dash
    return dash


def dashboard_configured(cfg: dict[str, Any]) -> bool:
    dash = _dashboard(cfg)
    return bool(str(dash.get("username") or "").strip()) and is_password_hash(str(dash.get("password_hash") or ""))


def totp_record(cfg: dict[str, Any]) -> dict[str, Any]:
    dash = _dashboard(cfg)
    totp = dash.get("totp")
    if not isinstance(totp, dict):
        totp = {}
        dash["totp"] = totp
    return totp


def totp_is_enabled(cfg: dict[str, Any]) -> bool:
    dash = cfg.get("dashboard") if isinstance(cfg.get("dashboard"), dict) else {}
    totp = dash.get("totp") if isinstance(dash, dict) else None
    if not isinstance(totp, dict):
        return False
    return bool(totp.get("enabled")) and bool(str(totp.get("secret") or ""))


def dashboard_password_ok(cfg: dict[str, Any], username: str, password: str) -> bool:
    dash = _dashboard(cfg)
    stored_user = str(dash.get("username") or "")
    stored_hash = str(dash.get("password_hash") or "")
    user_ok = hmac.compare_digest(
        hashlib.sha256(str(username or "").encode("utf-8")).digest(),
        hashlib.sha256(stored_user.encode("utf-8")).digest(),
    )
    if not is_password_hash(stored_hash):
        verify_password(str(password or ""), dummy_password_hash())
        return False
    password_ok = verify_password(str(password or ""), stored_hash)
    return bool(user_ok and password_ok)


def screen_known_default_hash(stored_hash: str) -> bool:
    """True when the hash verifies a published default and must be removed."""
    if not is_password_hash(stored_hash):
        return False
    for bad in KNOWN_DASHBOARD_DEFAULTS:
        if verify_password(bad, stored_hash):
            return True
    return False


def migrate_dashboard_secrets(cfg: dict[str, Any]) -> dict[str, bool]:
    """Hash a plaintext dashboard password in place. Never write a known default."""
    dash = _dashboard(cfg)
    changed = False
    removed_default = False
    hashed = False
    plain = dash.get("password")
    if isinstance(plain, str) and plain != "":
        if plain in KNOWN_DASHBOARD_DEFAULTS or plain.lower() in KNOWN_DASHBOARD_DEFAULTS:
            removed_default = True
        elif not is_password_hash(str(dash.get("password_hash") or "")):
            dash["password_hash"] = hash_password(plain)
            hashed = True
        dash.pop("password", None)
        changed = True
    stored = str(dash.get("password_hash") or "")
    if stored and not is_password_hash(stored):
        dash.pop("password_hash", None)
        changed = True
        stored = ""
    screened = bool(dash.get("defaults_screened"))
    if stored and not screened:
        if screen_known_default_hash(stored):
            dash.pop("password_hash", None)
            dash["password_removed"] = "known-default"
            removed_default = True
            stored = ""
        dash["defaults_screened"] = True
        changed = True
    elif not stored and not screened:
        dash["defaults_screened"] = True
        changed = True
    if not valid_session_key(str(cfg.get("session_key") or "")):
        cfg["session_key"] = new_session_key()
        # A new key invalidates every cookie issued by the previous process.
        dash["session_generation"] = int(dash.get("session_generation") or 0) + 1
        dash["revoked_sessions"] = []
        changed = True
    if "session_generation" not in dash:
        dash["session_generation"] = 1
        changed = True
    if not isinstance(dash.get("revoked_sessions"), list):
        dash["revoked_sessions"] = []
        changed = True
    return {"changed": changed, "hashed": hashed, "removed_default": removed_default}


def migrate_client_password(user: dict[str, Any]) -> bool:
    """Replace a plaintext client password with a hash of the folded secret. Returns True if changed."""
    raw = user.get("password")
    stored = str(user.get("password_hash") or "")
    changed = False
    if isinstance(raw, str) and raw != "":
        if is_password_hash(raw) and not is_password_hash(stored):
            user["password_hash"] = raw
        elif not is_password_hash(raw):
            user["password_hash"] = hash_client_password(raw)
        user.pop("password", None)
        changed = True
    elif stored and not is_password_hash(stored):
        user.pop("password_hash", None)
        changed = True
    return changed


def bump_session_generation(cfg: dict[str, Any]) -> int:
    dash = _dashboard(cfg)
    generation = int(dash.get("session_generation") or 0) + 1
    dash["session_generation"] = generation
    dash["revoked_sessions"] = []
    return generation


def issue_session(cfg: dict[str, Any], username: str) -> str:
    if not valid_session_key(str(cfg.get("session_key") or "")):
        raise RuntimeError("Session signing key is missing.")
    dash = _dashboard(cfg)
    payload = {
        "u": username,
        "g": int(dash.get("session_generation") or 0),
        "sid": secrets.token_hex(16),
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(bytes.fromhex(cfg["session_key"]), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"v2.{body}.{signature}"


def parse_session(cfg: dict[str, Any], token: str, *, ignore_revoked: bool = False) -> dict[str, Any] | None:
    parts = str(token or "").split(".")
    if len(parts) != 3 or parts[0] != "v2":
        return None
    if not valid_session_key(str(cfg.get("session_key") or "")):
        return None
    body, signature = parts[1], parts[2]
    expected = hmac.new(bytes.fromhex(cfg["session_key"]), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    username = str(payload.get("u") or "")
    sid = str(payload.get("sid") or "")
    try:
        generation = int(payload.get("g"))
        expires = int(payload.get("exp"))
    except (TypeError, ValueError):
        return None
    now = int(time.time())
    if expires < now or expires > now + SESSION_TTL_SECONDS + 60:
        return None
    if not username or not sid or len(sid) > 128:
        return None
    dash = _dashboard(cfg)
    if generation != int(dash.get("session_generation") or 0):
        return None
    if username != str(dash.get("username") or ""):
        return None
    revoked = dash.get("revoked_sessions") or []
    if not ignore_revoked and sid in revoked:
        return None
    return {"username": username, "sid": sid, "generation": generation, "exp": expires}


def revoke_session_id(cfg: dict[str, Any], sid: str) -> None:
    dash = _dashboard(cfg)
    revoked = [str(item) for item in (dash.get("revoked_sessions") or []) if str(item)]
    if sid and sid not in revoked:
        revoked.append(sid)
    dash["revoked_sessions"] = revoked[-100:]


def _hotp(secret: bytes, counter: int) -> str:
    digest = hmac.new(secret, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


def normalize_totp_code(code: str) -> str:
    return re.sub(r"\s+", "", str(code or ""))


def totp_secret_bytes(secret_b32: str) -> bytes | None:
    text = str(secret_b32 or "").strip().upper()
    if not text:
        return None
    pad = "=" * (-len(text) % 8)
    try:
        raw = base64.b32decode(text + pad, casefold=True)
    except (ValueError, TypeError):
        return None
    if len(raw) < 10:
        return None
    return raw


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_uri(secret_b32: str, username: str) -> str:
    label = f"Laneora:{username}"
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer=Laneora&algorithm=SHA1&digits=6&period=30"


def matching_totp_step(secret_b32: str, code: str, last_step: int) -> int | None:
    raw = totp_secret_bytes(secret_b32)
    code = normalize_totp_code(code)
    if raw is None or not re.fullmatch(r"\d{6}", code):
        return None
    now_step = int(time.time() // 30)
    matched: int | None = None
    for skew in (-1, 0, 1):
        step = now_step + skew
        if step <= int(last_step or 0):
            continue
        if hmac.compare_digest(_hotp(raw, step), code):
            matched = step
    return matched


def new_recovery_codes(count: int = 8) -> tuple[list[str], list[str]]:
    plain: list[str] = []
    hashed: list[str] = []
    for _ in range(count):
        code = secrets.token_urlsafe(16)
        salt = secrets.token_bytes(16)
        digest = hashlib.sha256(salt + code.encode("utf-8")).hexdigest()
        plain.append(code)
        hashed.append(f"sha256${_b64e(salt)}${digest}")
    return plain, hashed


def consume_recovery_code(code: str, hashes: list[str]) -> list[str] | None:
    candidate = str(code or "").strip()
    if len(candidate) < 16:
        return None
    kept: list[str] = []
    found = False
    for stored in hashes:
        try:
            algo, salt_text, digest_text = str(stored).split("$")
            if algo != "sha256":
                kept.append(str(stored))
                continue
            salt = _b64d(salt_text)
            digest = hashlib.sha256(salt + candidate.encode("utf-8")).hexdigest()
            if hmac.compare_digest(digest, digest_text):
                found = True
                continue
        except (ValueError, TypeError):
            pass
        kept.append(str(stored))
    if not found:
        return None
    return kept


def peer_ip(handler: Any) -> str:
    address = getattr(handler, "client_address", None)
    if address:
        return str(address[0])
    return ""


def trust_proxy(handler: Any) -> bool:
    mode = os.environ.get("LANEORA_TRUST_PROXY", "loopback").strip().lower()
    if mode in {"0", "off", "no", "false"}:
        return False
    if mode in {"1", "all", "yes", "true"}:
        return True
    return peer_ip(handler) in {"127.0.0.1", "::1"}


def client_ip(handler: Any) -> str:
    peer = peer_ip(handler) or "unknown"
    if not trust_proxy(handler):
        return peer
    headers = getattr(handler, "headers", None)
    if headers is None:
        return peer
    real = str(headers.get("X-Real-IP") or "").split(",")[0].strip()
    if real:
        return real
    forwarded = str(headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[-1].strip() or peer
    return peer


def request_host(handler: Any) -> str:
    headers = handler.headers
    if trust_proxy(handler):
        forwarded = str(headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return str(headers.get("Host") or "").strip()


def https_request(handler: Any) -> bool:
    forced = os.environ.get("LANEORA_COOKIE_SECURE", "").strip()
    if forced == "1":
        return True
    if forced == "0":
        return False
    headers = handler.headers
    if trust_proxy(handler):
        proto = str(headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        if proto == "https":
            return True
        host = request_host(handler).split(":")[0].strip("[]").lower()
        if host and host not in _LOCAL_HOSTS:
            return True
    return False


def origin_allowed(handler: Any) -> bool:
    headers = handler.headers
    origin = str(headers.get("Origin") or "").strip()
    if not origin:
        referer = str(headers.get("Referer") or "").strip()
        if not referer:
            return True
        parsed_referer = urlparse(referer)
        if parsed_referer.scheme not in {"http", "https"} or not parsed_referer.netloc:
            return False
        origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}"
    if origin == "null":
        return False
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.netloc.lower() != request_host(handler).lower():
        return False
    if parsed.scheme == "https":
        return https_request(handler) or trust_proxy(handler)
    return not https_request(handler)


def cookie_secure(handler: Any) -> bool:
    return https_request(handler)


def _prune(hits: dict[str, list[float]], key: str, window: float, now: float) -> list[float]:
    kept = [stamp for stamp in hits.get(key, []) if now - stamp < window]
    hits[key] = kept
    return kept


def throttle_blocked(bucket: str, key: str) -> bool:
    now = time.monotonic()
    with _throttle_lock:
        if bucket == "admin":
            hits = _prune(_admin_hits, key, ADMIN_LOGIN_WINDOW, now)
            return len(hits) >= ADMIN_LOGIN_LIMIT
        hits = _prune(_client_hits, key, CLIENT_AUTH_WINDOW, now)
        return len(hits) >= CLIENT_AUTH_LIMIT


def throttle_record(bucket: str, key: str) -> None:
    now = time.monotonic()
    with _throttle_lock:
        if bucket == "admin":
            hits = _prune(_admin_hits, key, ADMIN_LOGIN_WINDOW, now)
            hits.append(now)
            _admin_hits[key] = hits
            return
        hits = _prune(_client_hits, key, CLIENT_AUTH_WINDOW, now)
        hits.append(now)
        _client_hits[key] = hits


def throttle_clear(bucket: str, key: str) -> None:
    with _throttle_lock:
        if bucket == "admin":
            _admin_hits.pop(key, None)
        else:
            _client_hits.pop(key, None)


def reset_throttles() -> None:
    global _dummy_hash
    with _throttle_lock:
        _admin_hits.clear()
        _client_hits.clear()
    _dummy_hash = None


def redact_secrets(text: str) -> str:
    return _SECRET_QUERY.sub(r"\1\2=REDACTED", str(text))


def allow_get_authenticate() -> bool:
    return os.environ.get("LANEORA_ALLOW_GET_AUTH", "1").strip().lower() not in {"0", "off", "no", "false"}


def chmod_private(path: Any) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
