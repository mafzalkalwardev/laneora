"""Laneora desktop client."""

from app.config import SERVER_URL

__version__ = "3.0.0"
APP_NAME = "Laneora"
PASSPHRASE = "raw_value"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
ONE_DAT = "https://one.dat.com"
POWER_DAT = "https://power.dat.com"
SPEEDTEST_URL = "https://fast.com/"
IPINFO_URL = "https://ipinfo.io/json"

__all__ = [
    "APP_NAME",
    "SERVER_URL",
    "PASSPHRASE",
    "USER_AGENT",
    "ONE_DAT",
    "POWER_DAT",
    "SPEEDTEST_URL",
    "IPINFO_URL",
    "__version__",
]
