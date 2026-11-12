"""Pick unsolved problems that train a user's weakest tags at a slightly-too-hard level.
Works for Codeforces and LeetCode problems alike (both carry CF-scale ratings and CF tags)."""
from .problems import effective_rating, problem_key

IGNORED_TAGS = {"*special"}


def recommend(all_problems: list[dict], solved: set, weak_tags: list[str], level: int,
              n: int = 12, low: int = 0, high: int = 300) -> list[dict]:
    """Score = how weak the problem's tags are for this user + how close it is to level+100.

    - Only unsolved problems rated in [level+low, level+high] (official or predicted).
    - Each weak tag is worth more the weaker it is (first in the list = weakest).
    - Ties are broken by more solves (well-tested, fewer broken problems), so the output is stable.
    """
    weight = {t: len(weak_tags) - i for i, t in enumerate(weak_tags)}
    target = level + 100
    scored = []
    for p in all_problems:
        r = effective_rating(p)
        if r is None or not (level + low <= r <= level + high):
            continue
        if problem_key(p) in solved or IGNORED_TAGS & set(p["tags"]):
            continue
        hits = [t for t in p["tags"] if t in weight]
        if not hits:
            continue
        score = sum(weight[t] for t in hits) - abs(r - target) / 100
        scored.append((score, p["solved_count"], p, hits))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    out = []
    for score, _, p, hits in scored[:n]:
        reason = f"Trains {', '.join(hits)}; rated {effective_rating(p)}"
        if p["rating"] is None:
            reason += " (estimated)" if p.get("platform") == "lc" else " (predicted)"
        out.append({**p, "score": round(score, 2), "reason": reason})
    return out
