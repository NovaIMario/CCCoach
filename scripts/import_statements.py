"""Convert a scraped statements file (CFSeer's problems.json format) into data/statements.json.

    python -m scripts.import_statements path/to/problems.json

Input: a list of {"contest_id", "index", "name", "tags", "statement", ...}.
Output: {"<contest_id>/<index>": "<statement text>"}. Used by the problem page,
the AI hints and the tag model's training.
"""
import json
import sys

from app import config

if __name__ == "__main__":
    src = sys.argv[1]
    rows = json.load(open(src, encoding="utf-8"))
    out = {f"{r['contest_id']}/{r['index'].upper()}": r["statement"] for r in rows if r.get("statement")}
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / "statements.json").write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {len(out)} statements to {config.DATA_DIR / 'statements.json'}")
