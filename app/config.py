"""Settings, read once from the environment (and a local .env file if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("CCCOACH_DATA_DIR", ROOT / "data"))
MODELS_DIR = Path(os.getenv("CCCOACH_MODELS_DIR", ROOT / "models"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Running user code is the riskiest feature, so it can be switched off for public deploys.
ENABLE_CODE_RUNNER = os.getenv("ENABLE_CODE_RUNNER", "1") == "1"

# How long the cached Codeforces problemset stays fresh before it is re-downloaded.
PROBLEMSET_MAX_AGE_HOURS = float(os.getenv("PROBLEMSET_MAX_AGE_HOURS", "24"))

# LeetCode problem ratings are converted to the Codeforces scale as: CF ≈ LC − offset.
LC_RATING_OFFSET = int(os.getenv("LC_RATING_OFFSET", "600"))

# Set to 1 in tests and CI: never call Codeforces at startup, only use files in DATA_DIR.
OFFLINE = os.getenv("CCCOACH_OFFLINE", "0") == "1"

# Optional Postgres (e.g. Supabase) holding Codeforces statements: CFSeer's scraped `problems` table
# plus statements users paste in. Without it, pasted statements go to data/user_statements.json.
def _clean_url(value: str) -> str:
    """Forgive a common copy-paste slip in hosting dashboards: pasting the whole .env line
    (`DATABASE_URL=postgresql://...`) or quotes as the value."""
    value = value.strip().strip('"').strip("'")
    if value.upper().startswith("DATABASE_URL="):
        value = value.split("=", 1)[1].strip().strip('"').strip("'")
    return value


DATABASE_URL = _clean_url(os.getenv("DATABASE_URL", ""))
# How often the statements are re-read from the database (new scrapes / pastes from other servers).
STATEMENT_REFRESH_HOURS = float(os.getenv("STATEMENT_REFRESH_HOURS", "6"))
