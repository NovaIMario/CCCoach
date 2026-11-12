"""All Codeforces problems in memory, joined with contest info, solve counts,
optional statements and predicted ratings for problems Codeforces hasn't rated yet.

About 11,000 problems fit easily in memory, so search is a simple filter over a list.
"""
import json
import time
from pathlib import Path

from .codeforces import CodeforcesClient
from .ml.features import division


def _read_json(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    # accept a raw API response ({"status": "OK", "result": ...}) as well as just the result
    if isinstance(data, dict) and data.get("status") == "OK" and "result" in data:
        return data["result"]
    return data


def load_raw(data_dir: Path, client: CodeforcesClient | None, max_age_hours: float) -> tuple[dict, list[dict]]:
    """Return (problemset, contests). Uses files in data_dir when fresh, otherwise downloads
    and saves them. With client=None (offline) it only reads files."""
    ps_path, c_path = data_dir / "problemset.json", data_dir / "contests.json"
    fresh = ps_path.exists() and c_path.exists() and (time.time() - ps_path.stat().st_mtime) < max_age_hours * 3600
    if client is not None and not fresh:
        try:
            problemset, contests = client.problemset(), client.contests()
            data_dir.mkdir(parents=True, exist_ok=True)
            ps_path.write_text(json.dumps(problemset), encoding="utf-8")
            c_path.write_text(json.dumps(contests), encoding="utf-8")
            return problemset, contests
        except Exception:
            if not ps_path.exists():
                raise  # nothing cached to fall back on
    return _read_json(ps_path), _read_json(c_path)


def join(problemset: dict, contests: list[dict]) -> list[dict]:
    """Flatten the API response into one dict per problem."""
    by_id = {c["id"]: c for c in contests}
    solved = {(s["contestId"], s["index"]): s["solvedCount"] for s in problemset["problemStatistics"]}
    out = []
    for p in problemset["problems"]:
        if "contestId" not in p:
            continue
        c = by_id.get(p["contestId"], {})
        out.append({
            "platform": "cf",
            "contest_id": p["contestId"],
            "index": p["index"],
            "name": p["name"],
            "rating": p.get("rating"),
            "predicted_rating": None,
            "tags": p.get("tags", []),
            "solved_count": solved.get((p["contestId"], p["index"]), 0),
            "contest_name": c.get("name", ""),
            "contest_start": c.get("startTimeSeconds", 0),
            "division": division(c.get("name", "")),
        })
    return out


class ProblemStore:
    """`problems` are Codeforces problems; `lc_problems` are LeetCode problems on the CF scale."""

    def __init__(self, problems: list[dict], statements: dict[str, str] | None = None,
                 lc_problems: list[dict] | None = None):
        self.problems = problems
        self.by_key = {(p["contest_id"], p["index"]): p for p in problems}
        self.statements = statements or {}
        self.lc_problems = lc_problems or []
        self.lc_by_slug = {p["slug"]: p for p in self.lc_problems}
        self.tags = sorted({t for p in problems for t in p["tags"]})

    @classmethod
    def load(cls, data_dir: Path, client: CodeforcesClient | None, max_age_hours: float,
             lc_http=None, lc_offset: int = 600) -> "ProblemStore":
        from . import lc_problems
        problemset, contests = load_raw(data_dir, client, max_age_hours)
        statements = {}
        if (data_dir / "statements.json").exists():
            statements = _read_json(data_dir / "statements.json")
        lc = lc_problems.load(data_dir, lc_http, max_age_hours, lc_offset)
        return cls(join(problemset, contests), statements, lc)

    def fill_predicted_ratings(self, rating_model) -> int:
        """Predict a rating for every unrated problem that has been solved at least once."""
        todo = [p for p in self.problems if p["rating"] is None and p["solved_count"] > 0]
        for p, r in zip(todo, rating_model.predict(todo, self.problems)):
            p["predicted_rating"] = r
        return len(todo)

    def get(self, contest_id: int, index: str) -> dict | None:
        return self.by_key.get((contest_id, index.upper()))

    def statement(self, contest_id: int, index: str) -> str | None:
        return self.statements.get(f"{contest_id}/{index.upper()}")

    def search(self, name: str = "", tag: str = "", min_rating: int | None = None,
               max_rating: int | None = None, limit: int = 200, platform: str = "cf") -> list[dict]:
        name = name.lower().strip()
        pool = {"cf": self.problems, "lc": self.lc_problems}.get(platform, self.problems + self.lc_problems)
        out = []
        for p in pool:
            r = effective_rating(p)
            if name and name not in p["name"].lower():
                continue
            if tag and tag not in p["tags"]:
                continue
            if min_rating is not None and (r is None or r < min_rating):
                continue
            if max_rating is not None and (r is None or r > max_rating):
                continue
            out.append(p)
            if len(out) >= limit:
                break
        return out


def effective_rating(p: dict) -> int | None:
    """The official rating, or our prediction when Codeforces hasn't rated it."""
    return p["rating"] if p["rating"] is not None else p["predicted_rating"]


def problem_key(p: dict) -> tuple:
    """Unique id across platforms: (contest_id, index) for Codeforces, ("lc", slug) for LeetCode."""
    return ("lc", p["slug"]) if p.get("platform") == "lc" else (p["contest_id"], p["index"])
