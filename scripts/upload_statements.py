"""Copy data/statements.json into the database's cccoach_statements table (one-off).

    python -m scripts.upload_statements            # uses DATABASE_URL from .env

Only needed when the database doesn't already hold the statements in CFSeer's `problems`
table (e.g. a fresh Supabase project). Existing rows are left alone, so it is safe to re-run.
"""
import json

from app import config
from app.statements_db import PostgresStatements

BATCH = 500

if __name__ == "__main__":
    if not config.DATABASE_URL:
        raise SystemExit("Set DATABASE_URL in .env first")
    rows = json.loads((config.DATA_DIR / "statements.json").read_text(encoding="utf-8"))
    db = PostgresStatements(config.DATABASE_URL)
    already = db.load_all()
    todo = [(int(k.split("/")[0]), k.split("/")[1], v) for k, v in rows.items() if k not in already and v]
    print(f"{len(rows)} local statements, {len(already)} already in the database, uploading {len(todo)}")
    with db._connect() as conn, conn.cursor() as cur:
        for i in range(0, len(todo), BATCH):
            cur.executemany("INSERT INTO cccoach_statements (contest_id, problem_index, statement, source) "
                            "VALUES (%s, %s, %s, 'import') ON CONFLICT DO NOTHING", todo[i:i + BATCH])
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")
    print("Done")
