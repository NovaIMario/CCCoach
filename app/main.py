"""CCCoach web app: pages (Jinja templates) and a JSON API.

`create_app` takes its dependencies as arguments so tests can pass in fakes
instead of calling Codeforces, LeetCode or Gemini.
"""
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import analysis, config
from .ai import AIUnavailable, HintService, RateLimiter
from .codeforces import CodeforcesClient, CodeforcesError
from .lc_problems import LC_TO_CF_TAG
from .leetcode import LeetCodeClient, LeetCodeError
from .ml.models import load_models
from .problems import ProblemStore, effective_rating, split_cf_header
from .recommend import recommend
from .runner import LANGUAGES, run_code
from .statements_db import LocalStatements, clean_paste, open_backend

# A child of uvicorn's logger, so messages show up in the server output (and in Render's logs).
log = logging.getLogger("uvicorn.error." + __name__)

HERE = Path(__file__).resolve().parent


class RunRequest(BaseModel):
    language: str = "cpp"
    code: str = Field(max_length=100_000)
    stdin: str = Field("", max_length=1_000_000)


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|coach)$")
    text: str = Field(max_length=20_000)


class HintRequest(BaseModel):
    mode: str                       # hint | review | solution | chat
    contest_id: int | None = None   # Codeforces problem ...
    index: str | None = None
    slug: str | None = None         # ... or LeetCode problem
    code: str = Field("", max_length=100_000)
    message: str = Field("", max_length=2_000)            # chat mode only
    history: list[ChatTurn] = Field([], max_length=40)    # earlier turns; the service keeps the last 10


class StatementPaste(BaseModel):
    contest_id: int
    index: str = Field(max_length=4)
    statement: str = Field(max_length=40_000)  # cleaned and checked more strictly in clean_paste


class TagRequest(BaseModel):
    statement: str = Field(min_length=20, max_length=20_000)


def short_error(e: Exception) -> str:
    """First line of an error, without anything that looks like a password in a URL."""
    import re
    line = (str(e).strip().splitlines() or [type(e).__name__])[0]
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", line)[:200]


def create_app(store: ProblemStore | None = None, cf: CodeforcesClient | None = None,
               lc: LeetCodeClient | None = None, hints: HintService | None = None,
               rating_model=None, tag_model=None, code_runner_enabled: bool | None = None,
               statements=None) -> FastAPI:

    def sync_statements(s, stop: threading.Event):
        """Background thread: pull statements from the database now, then every few hours.
        Runs off the request path so a slow or paused database never delays startup."""
        while True:
            try:
                if isinstance(s.statements, LocalStatements) and config.DATABASE_URL and statements is None:
                    s.statements = open_backend(config.DATABASE_URL, config.DATA_DIR)  # retry the DB
                fresh = s.statements.load_all()
                added = sum(1 for k in fresh if k not in s.store.statements)
                for k, v in fresh.items():
                    s.store.statements.setdefault(k, v)
                log.info("Statements synced: %d from %s (%d new)", len(fresh), type(s.statements).__name__, added)
                s.statement_sync_error = s.statements.last_error if hasattr(s.statements, "last_error") else None
            except Exception as e:
                s.statement_sync_error = short_error(e)
                log.warning("Statement sync failed: %s", s.statement_sync_error)
            s.statement_sync_done.set()
            if stop.wait(config.STATEMENT_REFRESH_HOURS * 3600):
                return

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = app.state
        s.cf = cf or CodeforcesClient()
        s.lc = lc or LeetCodeClient()
        s.hints = hints or HintService(config.GEMINI_API_KEY, config.GEMINI_MODEL)
        if rating_model is None and tag_model is None:
            s.rating_model, s.tag_model = load_models(config.MODELS_DIR)
        else:
            s.rating_model, s.tag_model = rating_model, tag_model
        if store is not None:
            s.store = store
        else:
            online = not config.OFFLINE
            s.store = ProblemStore.load(config.DATA_DIR, s.cf if online else None, config.PROBLEMSET_MAX_AGE_HOURS,
                                        lc_http=s.lc.http if online else None, lc_offset=config.LC_RATING_OFFSET)
        if s.rating_model:
            s.store.fill_predicted_ratings(s.rating_model)
        s.runner_on = config.ENABLE_CODE_RUNNER if code_runner_enabled is None else code_runner_enabled
        s.limiter = RateLimiter(limit=10, window=60)
        s.paste_limiter = RateLimiter(limit=5, window=600)
        s.statement_misses: dict[str, float] = {}   # "cid/IDX" -> when the DB last had nothing
        if statements is not None:
            s.statements = statements
        else:
            s.statements = open_backend(config.DATABASE_URL, config.DATA_DIR)
        s.statement_sync_error = None
        s.statement_sync_done = threading.Event()  # set after the first sync (tests wait on it)
        stop = threading.Event()
        threading.Thread(target=sync_statements, args=(s, stop), daemon=True, name="statement-sync").start()
        yield
        stop.set()

    app = FastAPI(title="CCCoach", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    # Cache-buster for /static files: changes whenever any static file changes, so browsers
    # pick up new JS/CSS right after a deploy instead of serving a stale cached copy.
    templates.env.globals["v"] = max(int(f.stat().st_mtime) for f in (HERE / "static").iterdir())

    def page(request: Request, name: str, **ctx):
        return templates.TemplateResponse(request, name, ctx)

    # ---------- shared logic ----------

    def cf_data(handle: str) -> dict:
        """Everything we need from Codeforces about one user."""
        st = app.state
        try:
            info = st.cf.user_info(handle)
            history = st.cf.rating_history(handle)
            subs = st.cf.submissions(handle)
        except CodeforcesError as e:
            raise HTTPException(404, f"Codeforces: {e}")
        keys = analysis.solved_keys(subs)
        solved = [p for k in keys if (p := st.store.by_key.get(k))]
        return {
            "handle": info["handle"],
            "rank": info.get("rank", "unrated"),
            "stats": analysis.rating_stats(history),
            "solved_count": len(keys),
            "history": [{"t": c["ratingUpdateTimeSeconds"], "r": c["newRating"], "contest": c["contestName"]} for c in history],
            "solved_histogram": analysis.solved_rating_histogram(solved),
            "_solved": solved,
            "_solved_keys": keys,
        }

    def coach(cfd: dict | None, lcd: dict | None, n: int = 12) -> dict:
        """Combine Codeforces and/or LeetCode practice into one level, weak-tag list and two rec lists."""
        st = app.state
        solved = cfd["_solved"] if cfd else []
        if cfd:
            level = analysis.user_level(cfd["stats"], solved)
        elif lcd and lcd["contest_rating"]:
            level = max(800, lcd["contest_rating"] - config.LC_RATING_OFFSET)
        else:
            level = 1200
        extra = analysis.lc_tag_counts(lcd) if lcd else None
        tags = analysis.tag_profile(solved, st.store.problems, level, extra_counts=extra,
                                    extra_total=lcd["solved_total"] if lcd else 0,
                                    extra_tags=set(LC_TO_CF_TAG.values()) if lcd else set())
        weak = [t["tag"] for t in tags[:5]]
        cf_solved = cfd["_solved_keys"] if cfd else set()
        lc_solved = {("lc", s) for s in lcd["recent_solved"]} if lcd else set()
        return {
            "level": level,
            "tags": tags,
            "includes_lc": bool(lcd),
            # recommend only problems you can actually read here (stats above still use every problem)
            "cf_recs": recommend(st.store.with_statements(st.store.problems), cf_solved, weak, level, n=n),
            "lc_recs": recommend(st.store.lc_problems, lc_solved, weak, level, n=n),
        }

    def public(d: dict | None) -> dict | None:
        return {k: v for k, v in d.items() if not k.startswith("_")} if d else None

    def lc_profile_or_none(username: str) -> tuple[dict | None, str | None]:
        try:
            return app.state.lc.profile(username), None
        except Exception as e:  # LeetCode is optional: show the error, keep the page working
            return None, str(e)

    def resolve(contest_id: int | None, index: str | None, slug: str | None) -> tuple[dict, str]:
        """Find a problem on either platform and return it with its statement text."""
        st = app.state
        if slug:
            p = st.store.lc_by_slug.get(slug)
            if not p:
                raise HTTPException(404, "LeetCode problem not found")
            return p, st.lc.statement(slug) or ""
        p = st.store.get(contest_id or 0, index or "")
        if not p:
            raise HTTPException(404, "Problem not found")
        return p, st.store.statement(p["contest_id"], p["index"]) or lookup_statement(p) or ""

    def lookup_statement(p: dict) -> str | None:
        """Not in memory: ask the database once (someone may have pasted or scraped it since the
        last sync). Misses are remembered for 10 minutes so busy pages don't hammer the DB."""
        st = app.state
        k = f"{p['contest_id']}/{p['index'].upper()}"
        if time.time() - st.statement_misses.get(k, 0) < 600:
            return None
        try:
            text = st.statements.get(p["contest_id"], p["index"])
        except Exception as e:
            log.warning("Statement lookup failed: %s", e)
            text = None
        if text:
            st.store.statements[k] = text
        else:
            st.statement_misses[k] = time.time()
        return text

    # ---------- pages ----------

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "home.html")

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, cf: str = "", lc: str = ""):
        cf, lc = cf.strip(), lc.strip()
        ctx = {"cf_handle": cf, "lc_user": lc, "cf_error": None, "lc_error": None, "cf": None, "lc": None, "coach": None}
        cfd = lcd = None
        if cf:
            try:
                cfd = cf_data(cf)
            except HTTPException as e:
                ctx["cf_error"] = e.detail
        if lc:
            lcd, ctx["lc_error"] = lc_profile_or_none(lc)
        if cfd or lcd:
            ctx.update(cf=public(cfd), lc=lcd, coach=coach(cfd, lcd))
        return page(request, "profile.html", **ctx)

    @app.get("/compare", response_class=HTMLResponse)
    def compare_page(request: Request, a: str = "", b: str = ""):
        ctx = {"a": a, "b": b, "error": None, "pa": None, "pb": None, "winner": None}
        if a and b:
            try:
                da, db = cf_data(a.strip()), cf_data(b.strip())
                pa = {**public(da), "tags": coach(da, None, n=0)["tags"]}
                pb = {**public(db), "tags": coach(db, None, n=0)["tags"]}
                ctx.update(pa=pa, pb=pb, winner=analysis.compare(pa["stats"], pb["stats"]))
            except HTTPException as e:
                ctx["error"] = e.detail
        return page(request, "compare.html", **ctx)

    @app.get("/problems", response_class=HTMLResponse)
    def problems_page(request: Request):
        store = app.state.store
        return page(request, "problems.html", tags=store.tags,
                    names={"cf": [p["name"] for p in store.with_statements(store.problems)],
                           "lc": [p["name"] for p in store.lc_problems]})

    def problem_view(request: Request, p: dict, statement: str):
        is_lc = p.get("platform") == "lc"
        limits = None
        if not is_lc and statement:
            limits, statement = split_cf_header(statement)
        return page(request, "problem.html", p=p, is_lc=is_lc, rating=effective_rating(p), statement=statement, limits=limits,
                    title=(f"{p['frontend_id']}. {p['name']}" if is_lc else f"{p['contest_id']}{p['index']}. {p['name']}"),
                    ext_url=p["url"] if is_lc else f"https://codeforces.com/contest/{p['contest_id']}/problem/{p['index']}",
                    js_problem=({"slug": p["slug"]} if is_lc else {"contest_id": p["contest_id"], "index": p["index"]}),
                    runner_on=app.state.runner_on, hints_on=app.state.hints.enabled, languages=LANGUAGES)

    @app.get("/problem/{contest_id}/{index}", response_class=HTMLResponse)
    def problem_page(request: Request, contest_id: int, index: str):
        p, statement = resolve(contest_id, index, None)
        return problem_view(request, p, statement)

    @app.get("/lc/{slug}", response_class=HTMLResponse)
    def lc_problem_page(request: Request, slug: str):
        p, statement = resolve(None, None, slug)
        return problem_view(request, p, statement)

    @app.get("/predict", response_class=HTMLResponse)
    def predict_page(request: Request):
        tm, rm = app.state.tag_model, app.state.rating_model
        return page(request, "predict.html", tag_metrics=tm.metrics if tm else None,
                    rating_metrics=rm.metrics if rm else None)

    # ---------- JSON API ----------

    @app.get("/health")
    def health():
        st = app.state
        return {"ok": True, "problems": len(st.store.problems), "lc_problems": len(st.store.lc_problems),
                "rating_model": st.rating_model is not None, "tag_model": st.tag_model is not None,
                "code_runner": st.runner_on, "ai_hints": st.hints.enabled,
                # statement diagnostics (never the URL or password)
                "statements": len(st.store.statements), "database_configured": bool(config.DATABASE_URL),
                "statement_source": type(st.statements).__name__, "statement_sync_error": st.statement_sync_error}

    @app.get("/api/problems")
    def api_problems(name: str = "", tag: str = "", min_rating: int | None = None,
                     max_rating: int | None = None, limit: int = 200, platform: str = "cf"):
        return app.state.store.search(name, tag, min_rating, max_rating, min(limit, 1000), platform)

    @app.get("/api/profile/{handle}")
    def api_profile(handle: str):
        cfd = cf_data(handle)
        c = coach(cfd, None, n=0)
        return {**public(cfd), "level": c["level"], "tags": c["tags"]}

    @app.get("/api/recommend/{handle}")
    def api_recommend(handle: str, lc: str = "", n: int = 12):
        lcd = lc_profile_or_none(lc)[0] if lc else None
        c = coach(cf_data(handle), lcd, n=min(n, 50))
        return {"level": c["level"], "codeforces": c["cf_recs"], "leetcode": c["lc_recs"]}

    @app.get("/api/leetcode/{username}")
    def api_leetcode(username: str):
        try:
            return app.state.lc.profile(username)
        except LeetCodeError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/predict-rating/{contest_id}/{index}")
    def api_predict_rating(contest_id: int, index: str):
        p, _ = resolve(contest_id, index, None)
        if not app.state.rating_model:
            raise HTTPException(503, "Rating model not loaded")
        pred = app.state.rating_model.predict([p], app.state.store.problems)[0]
        return {"contest_id": contest_id, "index": p["index"], "name": p["name"], "solved_count": p["solved_count"],
                "official_rating": p["rating"], "predicted_rating": pred}

    @app.post("/api/predict-tags")
    def api_predict_tags(req: TagRequest):
        if not app.state.tag_model:
            raise HTTPException(503, "Tag model not loaded")
        return {"predictions": app.state.tag_model.predict(req.statement)}

    @app.post("/api/run")
    def api_run(req: RunRequest, request: Request):
        if not app.state.runner_on:
            raise HTTPException(403, "Code execution is disabled on this server")
        if req.language not in LANGUAGES:
            raise HTTPException(400, f"language must be one of {LANGUAGES}")
        if not app.state.limiter.allow(f"run:{request.client.host if request.client else '?'}"):
            raise HTTPException(429, "Too many runs, wait a minute")
        return run_code(req.language, req.code, req.stdin).to_dict()

    @app.post("/api/statement")
    def api_statement(req: StatementPaste, request: Request):
        """A user pastes a statement we don't have. It's saved for everyone (database or local file)."""
        st = app.state
        p = st.store.get(req.contest_id, req.index)
        if not p:
            raise HTTPException(404, "Problem not found")
        k = f"{p['contest_id']}/{p['index'].upper()}"
        if st.store.statements.get(k):
            raise HTTPException(409, "This problem already has a statement. Reload the page.")
        if not st.paste_limiter.allow(f"paste:{request.client.host if request.client else '?'}"):
            raise HTTPException(429, "Too many pasted statements, wait a few minutes")
        try:
            text = clean_paste(req.statement, p["name"])
        except ValueError as e:
            raise HTTPException(400, str(e))
        try:
            saved = st.statements.save(p["contest_id"], p["index"], text)
        except Exception as e:
            log.warning("Saving statement failed: %s", e)
            raise HTTPException(503, "Couldn't save the statement right now, try again later")
        if not saved:  # another server / the scraper got there first: use theirs
            text = st.statements.get(p["contest_id"], p["index"]) or text
        st.store.statements[k] = text
        st.statement_misses.pop(k, None)
        return {"ok": True, "saved": saved}

    @app.post("/api/hint")
    def api_hint(req: HintRequest, request: Request):
        p, statement = resolve(req.contest_id, req.index, req.slug)
        if not app.state.limiter.allow(f"hint:{request.client.host if request.client else '?'}"):
            raise HTTPException(429, "Too many requests, wait a minute")
        try:
            text = app.state.hints.ask(req.mode, p["name"], statement, req.code,
                                       message=req.message, history=[h.model_dump() for h in req.history])
        except ValueError as e:
            raise HTTPException(400, str(e))
        except AIUnavailable as e:
            return JSONResponse({"response": str(e)}, status_code=503)
        except Exception as e:
            return JSONResponse({"response": f"AI error: {e}"}, status_code=502)
        return {"response": text}

    return app


app = create_app()
