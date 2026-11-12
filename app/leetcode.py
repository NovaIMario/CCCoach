"""Read a LeetCode user's public stats through LeetCode's GraphQL endpoint."""
import time

import httpx

URL = "https://leetcode.com/graphql"
QUERY = """
query($u: String!) {
  matchedUser(username: $u) {
    submitStatsGlobal { acSubmissionNum { difficulty count } }
  }
  userContestRanking(username: $u) {
    rating globalRanking topPercentage attendedContestsCount badge { name }
  }
}
"""


class LeetCodeError(Exception):
    pass


class LeetCodeClient:
    def __init__(self, ttl: float = 600, http: httpx.Client | None = None):
        self.ttl = ttl
        self.http = http or httpx.Client(timeout=20, headers={"Referer": "https://leetcode.com", "User-Agent": "CPCoach/1.0"})
        self._cache: dict[str, tuple[float, dict]] = {}

    def profile(self, username: str) -> dict:
        hit = self._cache.get(username.lower())
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]

        resp = self.http.post(URL, json={"query": QUERY, "variables": {"u": username}})
        if resp.status_code != 200:
            raise LeetCodeError(f"LeetCode returned HTTP {resp.status_code}")
        data = resp.json().get("data") or {}
        if not data.get("matchedUser"):
            raise LeetCodeError(f"LeetCode user '{username}' not found")

        result = parse_profile(username, data)
        self._cache[username.lower()] = (time.time(), result)
        return result


def parse_profile(username: str, data: dict) -> dict:
    solved = {row["difficulty"]: row["count"] for row in data["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]}
    contest = data.get("userContestRanking") or {}
    return {
        "username": username,
        "solved_total": solved.get("All", 0),
        "solved": {d: solved.get(d, 0) for d in ("Easy", "Medium", "Hard")},
        "contest_rating": round(contest["rating"]) if contest.get("rating") else None,
        "top_percentage": contest.get("topPercentage"),
        "contests": contest.get("attendedContestsCount", 0),
        "badge": (contest.get("badge") or {}).get("name"),
    }
