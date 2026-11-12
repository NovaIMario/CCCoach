"""Turn a Codeforces user's history into stats and a weak-tag profile.

The weak-tag idea: around your rating, some fraction of problems carry each tag
(e.g. 12% are "dp"). If only 4% of the problems you solved are dp, dp is
under-practised for your level. We score each tag by

    weakness = expected_share / (your_share + smoothing)

so a high score means "you solve this tag much less than its share of problems
at your level".
"""
from collections import Counter

from .problems import effective_rating

IGNORED_TAGS = {"*special"}


def rating_stats(history: list[dict]) -> dict:
    if not history:
        return {"current": None, "peak": None, "contests": 0, "avg_change": 0.0, "best_gain": 0, "worst_drop": 0}
    changes = [c["newRating"] - c["oldRating"] for c in history]
    return {
        "current": history[-1]["newRating"],
        "peak": max(c["newRating"] for c in history),
        "contests": len(history),
        "avg_change": round(sum(changes) / len(changes), 1),
        "best_gain": max(changes),
        "worst_drop": min(changes),
    }


def solved_keys(submissions: list[dict]) -> set[tuple[int, str]]:
    return {
        (s["problem"]["contestId"], s["problem"]["index"])
        for s in submissions
        if s.get("verdict") == "OK" and "contestId" in s["problem"]
    }


def user_level(stats: dict, solved: list[dict]) -> int:
    """Current rating if the user has one, else the median rating of what they've solved."""
    if stats.get("current"):
        return stats["current"]
    rated = sorted(r for p in solved if (r := effective_rating(p)))
    return rated[len(rated) // 2] if rated else 1200


def tag_profile(solved: list[dict], all_problems: list[dict], level: int, window: int = 300,
                min_expected: int = 30) -> list[dict]:
    """Per tag: how much of the user's work it is vs how common it is around their level.
    Sorted weakest first."""
    nearby = [p for p in all_problems if (r := effective_rating(p)) and abs(r - level) <= window]
    nearby_counts = Counter(t for p in nearby for t in p["tags"] if t not in IGNORED_TAGS)
    solved_counts = Counter(t for p in solved for t in p["tags"] if t not in IGNORED_TAGS)
    n_nearby, n_solved = max(len(nearby), 1), max(len(solved), 1)

    out = []
    for tag, cnt in nearby_counts.items():
        if cnt < min_expected:
            continue  # too rare at this level to judge
        expected = cnt / n_nearby
        actual = solved_counts.get(tag, 0) / n_solved
        hardest = max((effective_rating(p) or 0 for p in solved if tag in p["tags"]), default=0)
        out.append({
            "tag": tag,
            "solved": solved_counts.get(tag, 0),
            "your_share": round(actual, 3),
            "expected_share": round(expected, 3),
            "weakness": round(expected / (actual + 0.01), 2),
            "hardest_solved": hardest or None,
        })
    return sorted(out, key=lambda t: -t["weakness"])


def solved_rating_histogram(solved: list[dict]) -> dict[int, int]:
    hist = Counter(r for p in solved if (r := effective_rating(p)))
    return dict(sorted(hist.items()))


def compare(stats_a: dict, stats_b: dict) -> dict:
    """Which user is ahead on each headline stat."""
    keys = ["current", "peak", "contests", "avg_change", "best_gain"]
    return {k: ("a" if (stats_a[k] or 0) > (stats_b[k] or 0) else "b" if (stats_b[k] or 0) > (stats_a[k] or 0) else "tie")
            for k in keys}
