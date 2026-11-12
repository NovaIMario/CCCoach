"""Small Codeforces API client with caching and rate limiting.

Codeforces allows roughly one request every two seconds per IP and returns
{"status": "FAILED", "comment": ...} for unknown handles, so every call goes through
`_get`, which waits between requests, caches results and turns failures into
`CodeforcesError`.
"""
import threading
import time

import httpx

API = "https://codeforces.com/api/"


class CodeforcesError(Exception):
    """The API answered, but with an error (e.g. handle not found)."""


class CodeforcesClient:
    def __init__(self, ttl: float = 600, min_interval: float = 0.6, http: httpx.Client | None = None):
        self.ttl = ttl
        self.min_interval = min_interval
        self.http = http or httpx.Client(timeout=30, headers={"User-Agent": "CPCoach/1.0"})
        self._cache: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._last_call = 0.0

    def _get(self, method: str, **params):
        key = (method, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]

        with self._lock:  # one request at a time, spaced out
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.http.get(API + method, params=params)
            finally:
                self._last_call = time.time()

        try:
            body = resp.json()
        except ValueError:
            raise CodeforcesError(f"Codeforces returned HTTP {resp.status_code}")
        if body.get("status") != "OK":
            raise CodeforcesError(body.get("comment", "Codeforces API error"))

        self._cache[key] = (time.time(), body["result"])
        return body["result"]

    def user_info(self, handle: str) -> dict:
        return self._get("user.info", handles=handle)[0]

    def rating_history(self, handle: str) -> list[dict]:
        return self._get("user.rating", handle=handle)

    def submissions(self, handle: str) -> list[dict]:
        return self._get("user.status", handle=handle)

    def problemset(self) -> dict:
        return self._get("problemset.problems", lang="en")

    def contests(self) -> list[dict]:
        return self._get("contest.list", gym="false")
