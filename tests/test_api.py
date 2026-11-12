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
    body = client.get("/api/recommend/alice").json()
    assert body["codeforces"]
    assert all(r["index"] in ("C", "D") for r in body["codeforces"])
    # LeetCode picks train weak tags too: the weakest (dp) first, the less weak (greedy) after
    lc = body["leetcode"]
    assert [("dp" in r["tags"]) for r in lc] == [True] * 5 + [False]


def test_lc_recommendations_skip_recently_solved(client):
    lc = client.get("/api/recommend/alice", params={"lc": "bob"}).json()["leetcode"]
    assert "lc-dp-1" not in {r["slug"] for r in lc}


def test_lc_search_and_page(client):
    res = client.get("/api/problems", params={"platform": "lc", "tag": "dp"}).json()
    assert len(res) == 5 and all(p["platform"] == "lc" for p in res)
    html = client.get("/lc/lc-dp-2").text
    assert "Statement of lc-dp-2" in html and "leetcode.com/problems/lc-dp-2" in html
    assert client.get("/lc/missing").status_code == 404


def test_lc_only_profile_uses_lc_rating(client):
    html = client.get("/profile?lc=bob").text
    assert "around 1200" in html   # 1800 LeetCode - 600 offset
    assert "Next on LeetCode" in html


def test_unknown_lc_user_keeps_cf_profile(client):
    html = client.get("/profile?cf=alice&lc=nobody").text
    assert "not found" in html and "Next on Codeforces" in html


def test_hint_for_lc_problem(client):
    r = client.post("/api/hint", json={"mode": "hint", "slug": "lc-dp-1"})
    assert r.json()["response"] == "hint for Lc Dp 1"


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


def test_hint_chat_mode(client):
    r = client.post("/api/hint", json={"mode": "chat", "contest_id": 1, "index": "A", "message": "why WA?",
                                       "history": [{"role": "user", "text": "hi"}, {"role": "coach", "text": "hello"}]})
    assert r.json()["response"] == "chat for Problem 1A: why WA? (2 earlier)"
    bad_role = {"mode": "chat", "contest_id": 1, "index": "A", "message": "x", "history": [{"role": "system", "text": "x"}]}
    assert client.post("/api/hint", json=bad_role).status_code == 422
    assert client.post("/api/hint", json={"mode": "chat", "contest_id": 1, "index": "A", "message": "x" * 2001}).status_code == 422
