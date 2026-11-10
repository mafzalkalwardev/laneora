"""Runtime config — soft.awwthat.com is the source of truth."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"  # Desktop roster (this PC's saved Soft logins)
LOCAL_USERS_FILE = DATA_DIR / "local_users.json"  # Server accounts + DAT streams
SOFT_CONFIG_FILE = DATA_DIR / "soft_config.json"  # Shared proxy, dashboard, session key


def data_dir() -> Path:
    """Server and roster files. LANEORA_DATA_DIR isolates tests and extra installs."""
    override = os.environ.get("LANEORA_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return DATA_DIR


def users_file() -> Path:
    return data_dir() / "users.json"


def local_users_file() -> Path:
    return data_dir() / "local_users.json"


def soft_config_file() -> Path:
    return data_dir() / "soft_config.json"


def write_private(path: Path, text: str) -> None:
    """Atomically replace a file and leave it readable only by the owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    tmp = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

# Default: local Soft shim on this PC. Override for LAN clients:
#   set LANEORA_SERVER_URL=http://192.168.1.20:8787
# Or production Soft later:
#   set LANEORA_SERVER_URL=https://soft.awwthat.com
SERVER_URL = os.environ.get("LANEORA_SERVER_URL", "http://127.0.0.1:8787").rstrip("/")

# When Soft /authenticate returns HTTP 5xx / is unreachable, Laneora can fall
# back to a local Soft-compatible shim (server/soft_shim.py).
SOFT_FALLBACK_URL = os.environ.get("LANEORA_SOFT_FALLBACK_URL", "http://127.0.0.1:8787").rstrip("/")
SOFT_FALLBACK = os.environ.get("LANEORA_SOFT_FALLBACK", "1") != "0"

# Skip update only when explicitly requested (local/offline experiments).
SKIP_UPDATE = os.environ.get("LANEORA_SKIP_UPDATE", "0") == "1"
