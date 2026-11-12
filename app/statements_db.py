"""Where Codeforces statements come from, besides the optional local data/statements.json.

Two backends with the same small interface:

* ``PostgresStatements`` (when DATABASE_URL is set, e.g. Supabase). Reads CFSeer's ``problems``
  table (filled by CFSeer's scraper) plus CCCoach's own ``cccoach_statements`` table, which holds
  statements users pasted in. Pasted text goes into the separate table so unverified user input
  never mixes with CFSeer's scraped training data.
* ``LocalStatements`` (no database): pasted statements are kept in data/user_statements.json.
  Fine for local use; on Render the disk is wiped on every deploy, so use the database there.

Interface: ``load_all() -> {"<contest>/<INDEX>": text}``, ``get(contest_id, index)``,
``save(contest_id, index, text) -> bool`` (False if a statement already existed).
"""
import json
import re
import logging
import threading
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cccoach_statements (
    contest_id    integer NOT NULL,
    problem_index text    NOT NULL,
    statement     text    NOT NULL,
    source        text    NOT NULL DEFAULT 'paste',
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (contest_id, problem_index)
)"""


def key(contest_id: int, index: str) -> str:
    return f"{int(contest_id)}/{index.upper()}"


class LocalStatements:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def load_all(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def get(self, contest_id: int, index: str) -> str | None:
        return self.load_all().get(key(contest_id, index))

    def save(self, contest_id: int, index: str, text: str) -> bool:
        with self.lock:
            data = self.load_all()
            k = key(contest_id, index)
            if k in data:
                return False
            data[k] = text
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.path)
            return True


class PostgresStatements:
    def __init__(self, url: str):
        self.url = url
        self.has_cfseer_table = False
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute("SELECT to_regclass('public.problems') IS NOT NULL")
            self.has_cfseer_table = cur.fetchone()[0]

    @contextmanager
    def _connect(self):
        """One short-lived connection: commit on success, roll back on error, ALWAYS close.
        (psycopg2's own `with conn:` only ends the transaction and would leak connections.)"""
        import psycopg2  # only needed when a database is configured
        conn = psycopg2.connect(self.url, sslmode="require", connect_timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _union(self, where: str = "") -> str:
        ours = f"SELECT contest_id, problem_index, statement FROM cccoach_statements {where}"
        if not self.has_cfseer_table:
            return ours
        cond = f"{where} AND statement IS NOT NULL" if where else "WHERE statement IS NOT NULL"
        # CFSeer's scraped statement wins over a pasted one when both exist.
        return f"SELECT contest_id, problem_index, statement FROM problems {cond} UNION ALL {ours}"

    def load_all(self) -> dict[str, str]:
        out: dict[str, str] = {}
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._union())
            for cid, idx, text in cur:
                out.setdefault(key(cid, idx), text)
        return out

    def get(self, contest_id: int, index: str) -> str | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(self._union("WHERE contest_id = %(c)s AND upper(problem_index) = %(i)s"),
                        {"c": int(contest_id), "i": index.upper()})
            row = cur.fetchone()
        return row[2] if row else None

    def save(self, contest_id: int, index: str, text: str) -> bool:
        if self.get(contest_id, index):
            return False
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO cccoach_statements (contest_id, problem_index, statement) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (int(contest_id), index.upper(), text))
            return cur.rowcount == 1


def open_backend(database_url: str, data_dir: Path):
    """The database if one is configured and reachable, else the local file."""
    if database_url:
        try:
            return PostgresStatements(database_url)
        except Exception as e:
            log.warning("Statement database unavailable (%s); using the local file", str(e).splitlines()[0])
    return LocalStatements(data_dir / "user_statements.json")


MIN_PASTE, MAX_PASTE = 150, 20_000


def clean_paste(text: str, problem_name: str) -> str:
    """Check that pasted text looks like THIS problem's statement and tidy it up.

    Pasted statements are shown to every user, so we refuse obvious junk: too short or too long,
    or text that doesn't mention the problem's name (a Codeforces page always starts with
    "E. <Name>"). It can't prove the text is genuine, but it stops accidents and lazy spam.
    """
    text = text.replace("\r\n", "\n").replace("\xa0", " ").strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) < MIN_PASTE:
        raise ValueError("That's too short to be the full statement. Copy the whole problem from Codeforces.")
    if len(text) > MAX_PASTE:
        raise ValueError("That's too long. Copy just the problem statement.")
    squash = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    if squash(problem_name) not in squash(text):
        raise ValueError(f'The pasted text doesn\'t mention "{problem_name}". Copy the statement starting from its title.')
    return text
