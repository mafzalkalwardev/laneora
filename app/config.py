"""Runtime config — local test server by default, override for production."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"

# Default: local Soft-compatible API for inject/test users.
# Override later with your own host, e.g.:
#   set LANEORA_SERVER_URL=https://soft.awwthat.com
#   set LANEORA_SERVER_URL=https://api.yourdomain.com
SERVER_URL = os.environ.get("LANEORA_SERVER_URL", "http://127.0.0.1:8787").rstrip("/")
SKIP_UPDATE = os.environ.get("LANEORA_SKIP_UPDATE", "1" if "127.0.0.1" in SERVER_URL or "localhost" in SERVER_URL else "0") == "1"
