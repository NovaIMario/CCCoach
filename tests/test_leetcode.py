from collections import Counter

from app import analysis
from app.lc_problems import build, map_tags
from app.leetcode import html_to_text, parse_profile

QUESTIONS = [
    {"questionFrontendId": "1", "title": "Two Sum", "titleSlug": "two-sum", "difficulty": "Easy", "isPaidOnly": False,
     "topicTags": [{"slug": "array"}, {"slug": "hash-table"}]},
    {"questionFrontendId": "2", "title": "Rated Medium", "titleSlug": "rated-medium", "difficulty": "Medium",
     "isPaidOnly": False, "topicTags": [{"slug": "dynamic-programming"}, {"slug": "binary-search"}]},
    {"questionFrontendId": "3", "title": "Unrated Medium", "titleSlug": "unrated-medium", "difficulty": "Medium",
     "isPaidOnly": False, "topicTags": [{"slug": "graph"}]},
    {"questionFrontendId": "4", "title": "Premium", "titleSlug": "premium", "difficulty": "Hard", "isPaidOnly": True,
     "topicTags": []},
]
ZEROTRAC = [{"TitleSlug": "rated-medium", "Rating": 1840.0}, {"TitleSlug": "two-sum", "Rating": 1100.0}]


def test_build_converts_ratings_with_offset():
    probs = {p["slug"]: p for p in build(QUESTIONS, ZEROTRAC, offset=600)}
    assert "premium" not in probs                          # paid-only problems are skipped
    assert probs["rated-medium"]["rating"] == 1200         # 1840 - 600 = 1240 -> nearest 100
    assert probs["two-sum"]["rating"] == 800               # clamped to the Codeforces minimum
    # unrated: median zerotrac rating of rated Mediums (1840) - 600, flagged as an estimate
    assert probs["unrated-medium"]["rating"] is None
    assert probs["unrated-medium"]["predicted_rating"] == 1200


def test_offset_is_configurable():
    probs = {p["slug"]: p for p in build(QUESTIONS, ZEROTRAC, offset=400)}
    assert probs["rated-medium"]["rating"] == 1400


def test_map_tags():
    assert map_tags(["dynamic-programming", "binary-search", "array"]) == ["binary search", "dp"]
    assert map_tags(["depth-first-search", "breadth-first-search"]) == ["dfs and similar"]


def test_parse_profile_reads_tag_counts_and_recent():
    data = {
        "matchedUser": {
            "submitStatsGlobal": {"acSubmissionNum": [{"difficulty": "All", "count": 9}, {"difficulty": "Easy", "count": 9}]},
            "tagProblemCounts": {"advanced": [{"tagSlug": "dynamic-programming", "problemsSolved": 4}],
                                 "intermediate": None,
                                 "fundamental": [{"tagSlug": "array", "problemsSolved": 9}]},
        },
        "userContestRanking": None,
        "recentAcSubmissionList": [{"titleSlug": "two-sum"}],
    }
    p = parse_profile("u", data)
    assert p["tag_counts"] == {"dynamic-programming": 4, "array": 9}
    assert p["recent_solved"] == ["two-sum"]
    assert p["contest_rating"] is None


def test_lc_tag_counts_map_to_cf_tags():
    counts = analysis.lc_tag_counts({"tag_counts": {"dynamic-programming": 4, "memoization": 2, "array": 9}})
    assert counts == Counter({"dp": 6})


def test_html_to_text():
    html = "<p>Given <code>n</code> &amp; 10<sup>5</sup> items.</p><ul><li>one</li><li>two</li></ul>"
    text = html_to_text(html)
    assert "Given n & 10^5 items." in text
    assert "one\n" in text and "<" not in text


def test_lc_practice_does_not_dilute_tags_lc_cannot_express(problems):
    solved = [p for p in problems if p["index"] in ("A", "B")]  # greedy/math/implementation
    base = {t["tag"]: t["your_share"] for t in analysis.tag_profile(solved, problems, 1500, min_expected=5)}
    # 1000 LeetCode solves that only ever express "dp": greedy's share must stay the same
    mixed = {t["tag"]: t["your_share"] for t in analysis.tag_profile(
        solved, problems, 1500, min_expected=5, extra_counts=Counter({"dp": 300}), extra_total=1000, extra_tags={"dp"})}
    assert mixed["greedy"] == base["greedy"]
    assert mixed["dp"] > base["dp"]


def test_lc_practice_counts_in_weak_tags(problems):
    # with no CF solves, LeetCode dp practice should make dp look less weak than graphs
    tags = analysis.tag_profile([], problems, level=1500, min_expected=5,
                                extra_counts=Counter({"dp": 50}), extra_total=60)
    order = [t["tag"] for t in tags]
    assert order.index("graphs") < order.index("dp")
