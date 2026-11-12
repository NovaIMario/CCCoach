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


def lc_tag_counts(lc_profile: dict) -> Counter:
    """LeetCode per-tag solve counts, mapped onto Codeforces tags.
    (A problem with two LC tags that map to the same CF tag, e.g. DFS and BFS, counts twice:
    an accepted approximation, since LeetCode doesn't publish the full solved list.)"""
    from .lc_problems import LC_TO_CF_TAG
    out = Counter()
    for slug, n in lc_profile.get("tag_counts", {}).items():
        if slug in LC_TO_CF_TAG:
            out[LC_TO_CF_TAG[slug]] += n
    return out


def lc_reported_tags(lc_profile: dict) -> set[str]:
    """Codeforces tags LeetCode actually reported counts for. LeetCode's public "skills" list covers
    a fixed set of tags and never includes some (e.g. number theory, combinatorics, geometry), even
    for users who solved hundreds of such problems; for those we must not assume 0 LeetCode solves."""
    from .lc_problems import LC_TO_CF_TAG
    return {LC_TO_CF_TAG[s] for s in lc_profile.get("tag_counts", {}) if s in LC_TO_CF_TAG}


def tag_profile(solved: list[dict], all_problems: list[dict], level: int, window: int = 300,
                min_expected: int = 30, extra_counts: Counter | None = None, extra_total: int = 0,
                extra_tags: set[str] | None = None) -> list[dict]:
    """Per tag: how much of the user's work it is vs how common it is around their level.
    Sorted weakest first.

    `extra_counts`/`extra_total` add practice from another platform (LeetCode). `extra_tags` is the
    set of tags that platform can express: for other tags (e.g. "constructive algorithms", which
    LeetCode has no tag for) only Codeforces solves are used, otherwise those tags would look weak
    just because LeetCode can't label them.
    """
    nearby = [p for p in all_problems if (r := effective_rating(p)) and abs(r - level) <= window]
    nearby_counts = Counter(t for p in nearby for t in p["tags"] if t not in IGNORED_TAGS)
    solved_counts = Counter(t for p in solved for t in p["tags"] if t not in IGNORED_TAGS)
    extra_counts = extra_counts or Counter()
    if extra_tags is None:
        extra_tags = set(extra_counts)
    n_nearby = max(len(nearby), 1)

    out = []
    for tag, cnt in nearby_counts.items():
        if cnt < min_expected:
            continue  # too rare at this level to judge
        expected = cnt / n_nearby
        if tag in extra_tags:
            solved_n, total = solved_counts.get(tag, 0) + extra_counts.get(tag, 0), len(solved) + extra_total
        elif solved:
            solved_n, total = solved_counts.get(tag, 0), len(solved)
        else:
            continue  # LeetCode-only user and LeetCode can't count this tag: no data, so don't call it weak
        actual = solved_n / max(total, 1)
        solved_counts[tag] = solved_n
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
