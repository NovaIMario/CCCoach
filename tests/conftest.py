"""Shared fixtures: a tiny fake problemset and fake API clients, so tests never touch the network."""
import pytest
from fastapi.testclient import TestClient

from app.codeforces import CodeforcesError
from app.main import create_app
from app.problems import ProblemStore


def make_problem(cid, idx, rating, tags, solved=1000, name=None):
    return {"contest_id": cid, "index": idx, "name": name or f"Problem {cid}{idx}", "rating": rating,
            "predicted_rating": None, "tags": tags, "solved_count": solved,
            "contest_name": "Codeforces Round (Div. 2)", "contest_start": 1.7e9, "division": "div2"}


@pytest.fixture
def problems():
    out = []
    for cid in range(1, 41):
        out += [
            make_problem(cid, "A", 800, ["implementation"], 20000),
            make_problem(cid, "B", 1200, ["greedy", "math"], 9000),
            make_problem(cid, "C", 1500, ["dp"] if cid % 2 else ["graphs"], 3000),
            make_problem(cid, "D", 1700, ["dp", "graphs"], 900),
            make_problem(cid, "E", None, ["data structures"], 200),
        ]
    return out


class FakeCF:
    def __init__(self, solved):
        self.solved = solved

    def user_info(self, handle):
        if handle == "ghost":
            raise CodeforcesError("handles: User with handle ghost not found")
        return {"handle": handle, "rank": "specialist"}

    def rating_history(self, handle):
        return [
            {"contestName": "Round 1", "oldRating": 0, "newRating": 1300, "ratingUpdateTimeSeconds": 1.6e9},
            {"contestName": "Round 2", "oldRating": 1300, "newRating": 1450, "ratingUpdateTimeSeconds": 1.61e9},
        ]

    def submissions(self, handle):
        return [{"verdict": "OK", "problem": {"contestId": c, "index": i}} for c, i in self.solved]


class FakeLC:
    def profile(self, username):
        return {"username": username, "solved_total": 10, "solved": {"Easy": 5, "Medium": 4, "Hard": 1},
                "contest_rating": 1800, "top_percentage": 10.0, "contests": 3, "badge": None}


class FakeHints:
    enabled = True

    def ask(self, mode, name, statement, code):
        if mode not in ("hint", "review", "solution"):
            raise ValueError("bad mode")
        return f"{mode} for {name}"


class FakeRatingModel:
    metrics = {}

    def predict(self, todo, all_problems):
        return [1900 for _ in todo]


@pytest.fixture
def client(problems):
    # the user has solved lots of greedy/math/implementation but no dp or graphs
    solved = [(c, i) for c in range(1, 41) for i in ("A", "B")]
    app = create_app(store=ProblemStore(problems, {"1/A": "Read $$$n$$$ and print it."}), cf=FakeCF(solved),
                     lc=FakeLC(), hints=FakeHints(), rating_model=FakeRatingModel(), code_runner_enabled=True)
    with TestClient(app) as c:
        yield c
