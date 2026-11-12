"""Read a LeetCode user's public stats, and problem statements, through LeetCode's GraphQL endpoint."""
import html
import re
import time

import httpx

URL = "https://leetcode.com/graphql"
QUERY = """
query($u: String!) {
  matchedUser(username: $u) {
    submitStatsGlobal { acSubmissionNum { difficulty count } }
    tagProblemCounts {
      advanced { tagSlug problemsSolved }
      intermediate { tagSlug problemsSolved }
      fundamental { tagSlug problemsSolved }
    }
  }
  userContestRanking(username: $u) {
    rating globalRanking topPercentage attendedContestsCount badge { name }
  }
  recentAcSubmissionList(username: $u, limit: 20) { titleSlug }
}
"""
QUESTION_QUERY = "query($s: String!) { question(titleSlug: $s) { content isPaidOnly } }"


class LeetCodeError(Exception):
    pass


class LeetCodeClient:
    def __init__(self, ttl: float = 600, http: httpx.Client | None = None):
        self.ttl = ttl
        self.http = http or httpx.Client(timeout=20, headers={"Referer": "https://leetcode.com", "User-Agent": "CCCoach/1.0"})
        self._cache: dict[str, tuple[float, dict]] = {}
        self._statements: dict[str, str | None] = {}

    def _post(self, query: str, variables: dict) -> dict:
        resp = self.http.post(URL, json={"query": query, "variables": variables})
        if resp.status_code != 200:
            raise LeetCodeError(f"LeetCode returned HTTP {resp.status_code}")
        return resp.json().get("data") or {}

    def profile(self, username: str) -> dict:
        hit = self._cache.get(username.lower())
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        data = self._post(QUERY, {"u": username})
        if not data.get("matchedUser"):
            raise LeetCodeError(f"LeetCode user '{username}' not found")
        result = parse_profile(username, data)
        self._cache[username.lower()] = (time.time(), result)
        return result

    def statement(self, slug: str) -> str | None:
        """Plain-text problem statement (None for Premium problems or on error). Cached forever."""
        if slug not in self._statements:
            try:
                q = self._post(QUESTION_QUERY, {"s": slug}).get("question") or {}
                self._statements[slug] = None if q.get("isPaidOnly") or not q.get("content") else html_to_text(q["content"])
            except Exception:
                return None  # don't cache failures
        return self._statements[slug]


def parse_profile(username: str, data: dict) -> dict:
    user = data["matchedUser"]
    solved = {row["difficulty"]: row["count"] for row in user["submitStatsGlobal"]["acSubmissionNum"]}
    contest = data.get("userContestRanking") or {}
    tag_counts = {}
    for level in (user.get("tagProblemCounts") or {}).values():
        for row in level or []:
            tag_counts[row["tagSlug"]] = row["problemsSolved"]
    return {
        "username": username,
        "solved_total": solved.get("All", 0),
        "solved": {d: solved.get(d, 0) for d in ("Easy", "Medium", "Hard")},
        "contest_rating": round(contest["rating"]) if contest.get("rating") else None,
        "top_percentage": contest.get("topPercentage"),
        "contests": contest.get("attendedContestsCount", 0),
        "badge": (contest.get("badge") or {}).get("name"),
        "tag_counts": tag_counts,
        # LeetCode only exposes the last 20 accepted problems publicly
        "recent_solved": [r["titleSlug"] for r in data.get("recentAcSubmissionList") or []],
    }


_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|pre|h\d)[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(content: str) -> str:
    """LeetCode statements are HTML. Keep line breaks, mark exponents, drop all other tags."""
    content = re.sub(r"<sup>(.*?)</sup>", r"^\1", content, flags=re.S)
    content = _BLOCK.sub("\n", content)
    content = html.unescape(_TAG.sub("", content)).replace("\xa0", " ")
    content = re.sub(r"[ \t]+\n", "\n", content)         # trailing spaces (LeetCode pads with &nbsp;)
    content = re.sub(r"\n[ \t]+(?=\n)", "\n", content)    # lines that are only spaces
    return re.sub(r"\n{3,}", "\n\n", content).strip()
