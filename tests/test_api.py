def test_health(client):
    body = client.get("/health").json()
    assert body["ok"] and body["problems"] == 200


def test_unrated_problems_get_predicted_ratings(client):
    p = client.get("/api/problems", params={"name": "Problem 1E"}).json()[0]
    assert p["rating"] is None and p["predicted_rating"] == 1900


def test_search_filters(client):
    res = client.get("/api/problems", params={"tag": "dp", "min_rating": 1600, "max_rating": 1800}).json()
    assert res and all(p["index"] == "D" for p in res)


def test_profile_api(client):
    body = client.get("/api/profile/alice").json()
    assert body["stats"]["current"] == 1450
    assert body["solved_count"] == 80
    assert "_solved_keys" not in body
    assert {t["tag"] for t in body["tags"][:2]} == {"dp", "graphs"}


def test_unknown_handle_is_404(client):
    assert client.get("/api/profile/ghost").status_code == 404


def test_recommendations_are_unsolved_weak_tag_problems(client):
    recs = client.get("/api/recommend/alice").json()
    assert recs
    assert all(r["index"] in ("C", "D") for r in recs)


def test_pages_render(client):
    for url in ["/", "/profile?cf=alice&lc=bob", "/compare?a=alice&b=carol", "/problems", "/problem/1/A", "/predict"]:
        r = client.get(url)
        assert r.status_code == 200, url
    assert "Read" in client.get("/problem/1/A").text


def test_profile_page_shows_error_for_unknown_handle(client):
    assert "not found" in client.get("/profile?cf=ghost").text


def test_html_is_escaped(client, problems):
    problems[0]["name"] = "<script>alert(1)</script>"
    html = client.get("/problem/1/A").text
    assert "<script>alert(1)</script>" not in html


def test_run_endpoint(client):
    r = client.post("/api/run", json={"language": "python", "code": "print(input()[::-1])", "stdin": "abc"})
    assert r.json()["stdout"].strip() == "cba"


def test_run_rejects_unknown_language(client):
    assert client.post("/api/run", json={"language": "cobol", "code": "x"}).status_code == 400


def test_hint_modes(client):
    assert client.post("/api/hint", json={"mode": "hint", "contest_id": 1, "index": "A"}).json()["response"] == "hint for Problem 1A"
    assert client.post("/api/hint", json={"mode": "anything", "contest_id": 1, "index": "A"}).status_code == 400


def test_leetcode(client):
    assert client.get("/api/leetcode/bob").json()["contest_rating"] == 1800
