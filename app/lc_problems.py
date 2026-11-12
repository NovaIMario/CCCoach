"""LeetCode problems on the Codeforces rating scale.

Sources:
  - LeetCode GraphQL `questionList`: every problem with difficulty, tags, paid-only flag.
  - zerotrac's LeetCode problem ratings (https://zerotrac.github.io/leetcode_problem_rating/):
    an Elo-style rating for ~2,600 weekly/biweekly contest problems, on LeetCode's contest scale.

Conversion: CF rating ≈ LeetCode rating − LC_RATING_OFFSET (default 600, a common rule of thumb,
configurable). Problems without a zerotrac rating get the median zerotrac rating of their
difficulty (Easy/Medium/Hard), computed from the data, and are marked as estimated.

LeetCode tags are mapped onto Codeforces tags so both platforms share one weak-tag analysis.
Tags with no Codeforces equivalent (array, hash-table, ...) are kept in `lc_tags` only.
"""
import json
import statistics
import time
from pathlib import Path

import httpx

LC_GRAPHQL = "https://leetcode.com/graphql"
ZEROTRAC_URL = "https://zerotrac.github.io/leetcode_problem_rating/data.json"

LIST_QUERY = """
query($skip: Int, $limit: Int) {
  questionList(categorySlug: "", limit: $limit, skip: $skip, filters: {}) {
    totalNum
    data { questionFrontendId title titleSlug difficulty isPaidOnly topicTags { slug } }
  }
}
"""

LC_TO_CF_TAG = {
    "dynamic-programming": "dp", "memoization": "dp",
    "greedy": "greedy",
    "math": "math",
    "graph": "graphs", "topological-sort": "graphs", "eulerian-circuit": "graphs",
    "tree": "trees", "binary-tree": "trees", "minimum-spanning-tree": "trees",
    "depth-first-search": "dfs and similar", "breadth-first-search": "dfs and similar",
    "binary-search": "binary search",
    "sorting": "sortings",
    "string": "strings",
    "two-pointers": "two pointers", "sliding-window": "two pointers",
    "bit-manipulation": "bitmasks", "bitmask": "bitmasks",
    "union-find": "dsu",
    "number-theory": "number theory",
    "combinatorics": "combinatorics",
    "geometry": "geometry",
    "hash-function": "hashing", "rolling-hash": "hashing", "string-matching": "strings",
    "segment-tree": "data structures", "binary-indexed-tree": "data structures",
    "heap-priority-queue": "data structures", "monotonic-stack": "data structures",
    "monotonic-queue": "data structures", "ordered-set": "data structures", "trie": "data structures",
    "shortest-path": "shortest paths",
    "game-theory": "games",
    "simulation": "implementation",
    "brute-force": "brute force", "backtracking": "brute force", "enumeration": "brute force",
    "probability-and-statistics": "probabilities",
    "divide-and-conquer": "divide and conquer",
    "interactive": "interactive",
    "matrix": "implementation",
}


def map_tags(lc_tags: list[str]) -> list[str]:
    return sorted({LC_TO_CF_TAG[t] for t in lc_tags if t in LC_TO_CF_TAG})


def fetch_question_list(http: httpx.Client, page: int = 100) -> list[dict]:
    out = []
    while True:
        resp = http.post(LC_GRAPHQL, json={"query": LIST_QUERY, "variables": {"skip": len(out), "limit": page}})
        resp.raise_for_status()
        data = resp.json()["data"]["questionList"]
        out += data["data"]
        # LeetCode may return fewer than `limit` per page, so advance by what we actually got
        if len(out) >= data["totalNum"] or not data["data"]:
            return out


def build(questions: list[dict], zerotrac: list[dict], offset: int) -> list[dict]:
    """Join LeetCode's list with zerotrac ratings and convert to the CF scale."""
    rating = {z["TitleSlug"]: z["Rating"] for z in zerotrac}
    diff_of = {q["titleSlug"]: q["difficulty"] for q in questions}
    medians = {}
    for d in ("Easy", "Medium", "Hard"):
        rated = [r for slug, r in rating.items() if diff_of.get(slug) == d]
        medians[d] = statistics.median(rated) if rated else {"Easy": 1300, "Medium": 1650, "Hard": 2100}[d]

    out = []
    for q in questions:
        if q.get("isPaidOnly"):
            continue  # can't be solved without Premium
        lc_tags = [t["slug"] for t in q.get("topicTags") or []]
        exact = rating.get(q["titleSlug"])
        lc_rating = exact if exact is not None else medians.get(q["difficulty"], 1650)
        cf_rating = max(800, int(round((lc_rating - offset) / 100) * 100))
        out.append({
            "platform": "lc",
            "slug": q["titleSlug"],
            "frontend_id": q["questionFrontendId"],
            "name": q["title"],
            "difficulty": q["difficulty"],
            "lc_tags": lc_tags,
            "tags": map_tags(lc_tags),
            # "rating" = converted contest rating; "predicted_rating" = difficulty-based estimate
            "rating": cf_rating if exact is not None else None,
            "predicted_rating": None if exact is not None else cf_rating,
            "lc_rating": round(lc_rating),
            "solved_count": 0,
            "url": f"https://leetcode.com/problems/{q['titleSlug']}/",
        })
    return out


def load(data_dir: Path, http: httpx.Client | None, max_age_hours: float, offset: int) -> list[dict]:
    """Cached in data/lc_raw.json. Offline (http=None) uses the cache only; any failure returns []
    so LeetCode support never stops the app from starting."""
    path = data_dir / "lc_raw.json"
    fresh = path.exists() and (time.time() - path.stat().st_mtime) < max_age_hours * 3600
    raw = None
    if http is not None and not fresh:
        try:
            raw = {"questions": fetch_question_list(http), "zerotrac": http.get(ZEROTRAC_URL).raise_for_status().json()}
            data_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw), encoding="utf-8")
        except Exception:
            raw = None
    if raw is None and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    return build(raw["questions"], raw["zerotrac"], offset)
