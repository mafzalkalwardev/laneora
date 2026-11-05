"""Runtime config — soft.awwthat.com is the source of truth."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"  # Soft credentials roster (username/password)
LOCAL_USERS_FILE = DATA_DIR / "local_users.json"  # Soft-compatible accounts + DAT streams
SOFT_CONFIG_FILE = DATA_DIR / "soft_config.json"  # Shared proxy IP + multi-PC policy

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
