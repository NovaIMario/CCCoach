"""Feature engineering shared by training scripts and the running app.

Keeping this in one place means the model always sees features computed the
same way at training time and at prediction time.
"""
import math
import re
from collections import defaultdict

import numpy as np

DIVISIONS = ["div1", "div2", "div3", "div4", "div12", "edu", "global", "other"]


def division(contest_name: str) -> str:
    n = contest_name.lower()
    if "div. 1 + div. 2" in n or "div.1 + div.2" in n:
        return "div12"
    if "educational" in n:
        return "edu"
    if "global" in n:
        return "global"
    for d in ("div. 1", "div. 2", "div. 3", "div. 4"):
        if d in n:
            return d.replace(". ", "")
    return "other"


def letter_position(index: str) -> tuple[int, int]:
    """'C' -> (2, 0), 'E2' -> (4, 2). Later letters are usually harder."""
    m = re.match(r"([A-Z])(\d*)", index.upper())
    if not m:
        return 0, 0
    return ord(m.group(1)) - 65, int(m.group(2) or 0)


def contest_stats(problems: list[dict]) -> dict[int, dict]:
    """Per contest: how many problems it has and the solve count of its most-solved problem."""
    solves = defaultdict(list)
    for p in problems:
        solves[p["contest_id"]].append(p.get("solved_count") or 0)
    return {cid: {"n": len(s), "max_solved": max(s)} for cid, s in solves.items()}


def rating_features(problems: list[dict], stats: dict[int, dict], tag_vocab: list[str]) -> np.ndarray:
    """One row per problem. Each problem dict needs contest_id, index, solved_count,
    tags, contest_name and contest_start (seconds)."""
    tag_pos = {t: i for i, t in enumerate(tag_vocab)}
    rows = np.zeros((len(problems), 6 + len(DIVISIONS) + len(tag_vocab)))
    for r, p in enumerate(problems):
        cs = stats.get(p["contest_id"], {"n": 1, "max_solved": p.get("solved_count") or 0})
        log_solved = math.log1p(p.get("solved_count") or 0)
        letter, sub = letter_position(p["index"])
        rows[r, 0] = log_solved
        rows[r, 1] = letter
        rows[r, 2] = sub
        rows[r, 3] = cs["n"]
        rows[r, 4] = log_solved - math.log1p(cs["max_solved"])  # solves relative to the contest's easiest problem
        rows[r, 5] = (p.get("contest_start") or 0) / 3.15e7       # roughly "year", since Codeforces grew over time
        rows[r, 6 + DIVISIONS.index(division(p.get("contest_name", "")))] = 1
        for t in p.get("tags", []):
            if t in tag_pos:
                rows[r, 6 + len(DIVISIONS) + tag_pos[t]] = 1
    return rows


_HEADER = re.compile(r"^.*?output\s+standard output\s+", re.S | re.I)
_MATH = re.compile(r"\$\$\$.*?\$\$\$", re.S)


def clean_statement(text: str) -> str:
    """Drop the 'C. Name time limit ... standard output' header and turn formulas into one token."""
    text = _HEADER.sub("", text, count=1)
    return _MATH.sub(" MATH ", text)
