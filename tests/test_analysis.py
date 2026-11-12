from app import analysis
from app.recommend import recommend


def test_rating_stats():
    history = [{"oldRating": 0, "newRating": 1400}, {"oldRating": 1400, "newRating": 1350},
               {"oldRating": 1350, "newRating": 1600}]
    s = analysis.rating_stats(history)
    assert s == {"current": 1600, "peak": 1600, "contests": 3, "avg_change": 533.3, "best_gain": 1400, "worst_drop": -50}


def test_rating_stats_empty():
    assert analysis.rating_stats([])["current"] is None


def test_solved_keys_only_counts_accepted():
    subs = [{"verdict": "OK", "problem": {"contestId": 1, "index": "A"}},
            {"verdict": "WRONG_ANSWER", "problem": {"contestId": 1, "index": "B"}},
            {"verdict": "OK", "problem": {"contestId": 1, "index": "A"}},
            {"verdict": "OK", "problem": {"index": "A"}}]  # gym/acmsguru problem without contestId
    assert analysis.solved_keys(subs) == {(1, "A")}


def test_weak_tags_are_the_ones_never_solved(problems):
    solved = [p for p in problems if p["index"] in ("A", "B")]
    tags = analysis.tag_profile(solved, problems, level=1500, min_expected=5)
    weakest = {t["tag"] for t in tags[:2]}
    assert weakest == {"dp", "graphs"}
    assert tags[-1]["tag"] in {"greedy", "math"}


def test_user_level_falls_back_to_median_solved(problems):
    solved = [p for p in problems if p["index"] == "B"]
    assert analysis.user_level({"current": None}, solved) == 1200


def test_recommend_targets_weak_tags_above_level(problems):
    solved = {(p["contest_id"], p["index"]) for p in problems if p["index"] in ("A", "B")}
    recs = recommend(problems, solved, ["dp", "graphs"], level=1450, n=5)
    assert len(recs) == 5
    for r in recs:
        assert (r["contest_id"], r["index"]) not in solved
        assert 1450 <= r["rating"] <= 1750
        assert {"dp", "graphs"} & set(r["tags"])

    # dp is weaker than graphs, so every dp problem must rank above every graphs-only problem
    ranked = recommend(problems, solved, ["dp", "graphs"], level=1450, n=1000)
    has_dp = [("dp" in r["tags"]) for r in ranked]
    assert has_dp == sorted(has_dp, reverse=True)


def test_recommend_skips_solved(problems):
    everything = {(p["contest_id"], p["index"]) for p in problems}
    assert recommend(problems, everything, ["dp"], level=1400) == []
