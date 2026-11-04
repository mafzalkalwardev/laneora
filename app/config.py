"""Runtime config — soft.awwthat.com is the source of truth."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"  # Soft credentials roster (username/password)
LOCAL_USERS_FILE = DATA_DIR / "local_users.json"  # Optional local Soft-compatible API accounts

# Default: production Soft API. Override later for your own host:
#   set LANEORA_SERVER_URL=https://api.yourdomain.com
SERVER_URL = os.environ.get("LANEORA_SERVER_URL", "https://soft.awwthat.com").rstrip("/")

# Skip update only when explicitly requested (local/offline experiments).
SKIP_UPDATE = os.environ.get("LANEORA_SKIP_UPDATE", "0") == "1"
