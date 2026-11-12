import pytest

from app.statements_db import LocalStatements, clean_paste

STATEMENT = ("C. Problem 3C\ntime limit per test 1 second\nmemory limit per test 256 megabytes\n\n"
             "You are given an array of n integers. Find the maximum sum of a contiguous subarray. "
             "Print a single integer, the answer.\n\nInput\nThe first line contains n.\n")


def test_database_statements_are_loaded_at_startup(client):
    page = client.get("/problem/2/A").text
    assert "Statement from the database." in page
    assert "paste-form" not in page


def test_missing_statement_shows_paste_box(client):
    page = client.get("/problem/3/C").text
    assert "paste-form" in page and "have this statement yet" in page


def test_paste_saves_statement_for_everyone(client):
    r = client.post("/api/statement", json={"contest_id": 3, "index": "C", "statement": STATEMENT})
    assert r.status_code == 200 and r.json()["saved"] is True
    assert client.app.state.statements.get(3, "C").startswith("C. Problem 3C")   # stored in the backend
    page = client.get("/problem/3/C").text
    assert "Find the maximum sum" in page and "paste-form" not in page
    assert "Time limit 1 second" in page                                          # header split out
    # a second paste can't overwrite it
    again = client.post("/api/statement", json={"contest_id": 3, "index": "C", "statement": STATEMENT + "x"})
    assert again.status_code == 409


def test_paste_is_validated(client):
    short = client.post("/api/statement", json={"contest_id": 3, "index": "D", "statement": "too short"})
    assert short.status_code == 400
    wrong = client.post("/api/statement", json={"contest_id": 3, "index": "D", "statement": STATEMENT})
    assert wrong.status_code == 400 and "Problem 3D" in wrong.json()["detail"]   # it's 3C's text
    assert client.post("/api/statement", json={"contest_id": 999, "index": "Z", "statement": STATEMENT}).status_code == 404


def test_paste_is_rate_limited(client):
    codes = [client.post("/api/statement", json={"contest_id": 4, "index": "A", "statement": "x"}).status_code
             for _ in range(6)]
    assert codes[:5] == [400] * 5 and codes[5] == 429


def test_clean_paste_tidies_whitespace():
    text = clean_paste("  C. Problem   3C \r\n\r\n\r\n\r\n" + "word " * 40, "Problem 3C")
    assert "\r" not in text and "\n\n\n" not in text and text.startswith("C. Problem")
    with pytest.raises(ValueError):
        clean_paste("x" * 30_000 + " Problem 3C", "Problem 3C")


def test_local_backend_round_trip(tmp_path):
    store = LocalStatements(tmp_path / "user_statements.json")
    assert store.load_all() == {} and store.get(5, "b") is None
    assert store.save(5, "b", "text") is True
    assert store.save(5, "B", "other") is False          # first one wins, index case-insensitive
    assert LocalStatements(tmp_path / "user_statements.json").get(5, "B") == "text"


def test_health_reports_statement_source(client):
    h = client.get("/health").json()
    assert h["statements"] == len(client.app.state.store.statements) and h["statement_source"] == "FakeStatements" and h["statement_sync_error"] is None


def test_short_error_hides_passwords():
    from app.main import short_error
    msg = short_error(Exception("could not connect postgresql://postgres.abc:s3cret@host:5432/db\nmore"))
    assert "s3cret" not in msg and "postgres.abc:***@host" in msg


def test_database_url_paste_slips_are_forgiven():
    from app.config import _clean_url
    url = "postgresql://u:p@host:5432/db"
    for raw in (url, f"DATABASE_URL={url}", f'DATABASE_URL="{url}"', f"  '{url}'  "):
        assert _clean_url(raw) == url
    assert _clean_url("") == ""


def test_problems_without_statement_are_hidden_from_lists(client):
    hidden = lambda ps: [p for p in ps if p.get("platform") != "lc" and p["contest_id"] in (3, 4)]
    found = client.get("/api/problems", params={"limit": 1000}).json()
    assert found and not hidden(found)
    assert any(p["contest_id"] == 2 for p in found)        # statement came from the database
    everything = client.get("/api/problems", params={"limit": 1000, "platform": "all"}).json()
    assert any(p.get("platform") == "lc" for p in everything) and not hidden(everything)
    recs = client.get("/api/recommend/tester").json()["codeforces"]
    assert recs and not hidden(recs)
    page = client.get("/problems").text
    assert "Problem 3C" not in page and "Problem 5A" in page   # autocomplete names


def test_hidden_problem_still_opens_by_direct_link_and_appears_once_pasted(client):
    from tests.test_statements import STATEMENT
    assert client.get("/problem/3/C").status_code == 200       # paste box, as before
    client.post("/api/statement", json={"contest_id": 3, "index": "C", "statement": STATEMENT})
    found = client.get("/api/problems", params={"name": "Problem 3C"}).json()
    assert [p["index"] for p in found] == ["C"]
