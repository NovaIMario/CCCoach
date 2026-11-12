"""Settings, read once from the environment (and a local .env file if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("CPCOACH_DATA_DIR", ROOT / "data"))
MODELS_DIR = Path(os.getenv("CPCOACH_MODELS_DIR", ROOT / "models"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Running user code is the riskiest feature, so it can be switched off for public deploys.
ENABLE_CODE_RUNNER = os.getenv("ENABLE_CODE_RUNNER", "1") == "1"

# How long the cached Codeforces problemset stays fresh before it is re-downloaded.
PROBLEMSET_MAX_AGE_HOURS = float(os.getenv("PROBLEMSET_MAX_AGE_HOURS", "24"))

# Set to 1 in tests and CI: never call Codeforces at startup, only use files in DATA_DIR.
OFFLINE = os.getenv("CPCOACH_OFFLINE", "0") == "1"
