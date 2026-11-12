"""CCCoach web app: pages (Jinja templates) and a JSON API.

`create_app` takes its dependencies as arguments so tests can pass in fakes
instead of calling Codeforces, LeetCode or Gemini.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import analysis, config
from .ai import HintService, RateLimiter
from .codeforces import CodeforcesClient, CodeforcesError
from .leetcode import LeetCodeClient, LeetCodeError
from .ml.models import load_models
from .problems import ProblemStore, effective_rating
from .recommend import recommend
from .runner import LANGUAGES, run_code

HERE = Path(__file__).resolve().parent


class RunRequest(BaseModel):
    language: str = "cpp"
    code: str = Field(max_length=100_000)
    stdin: str = Field("", max_length=1_000_000)


class HintRequest(BaseModel):
    mode: str
    contest_id: int
    index: str
    code: str = Field("", max_length=100_000)


class TagRequest(BaseModel):
    statement: str = Field(min_length=20, max_length=20_000)


def create_app(store: ProblemStore | None = None, cf: CodeforcesClient | None = None,
               lc: LeetCodeClient | None = None, hints: HintService | None = None,
               rating_model=None, tag_model=None, code_runner_enabled: bool | None = None) -> FastAPI:

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
        s.store = store or ProblemStore.load(config.DATA_DIR, None if config.OFFLINE else s.cf,
                                             config.PROBLEMSET_MAX_AGE_HOURS)
        if s.rating_model:
            s.store.fill_predicted_ratings(s.rating_model)
        s.runner_on = config.ENABLE_CODE_RUNNER if code_runner_enabled is None else code_runner_enabled
        s.limiter = RateLimiter(limit=10, window=60)
        yield

    app = FastAPI(title="CCCoach", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def page(request: Request, name: str, **ctx):
        return templates.TemplateResponse(request, name, ctx)

    # ---------- shared logic ----------

    def cf_profile(handle: str) -> dict:
        st = app.state
        try:
            info = st.cf.user_info(handle)
            history = st.cf.rating_history(handle)
            subs = st.cf.submissions(handle)
        except CodeforcesError as e:
            raise HTTPException(404, f"Codeforces: {e}")
        stats = analysis.rating_stats(history)
        keys = analysis.solved_keys(subs)
        solved = [p for k in keys if (p := st.store.by_key.get(k))]
        level = analysis.user_level(stats, solved)
        tags = analysis.tag_profile(solved, st.store.problems, level)
        return {
            "handle": info["handle"],
            "rank": info.get("rank", "unrated"),
            "stats": stats,
            "level": level,
            "solved_count": len(keys),
            "history": [{"t": c["ratingUpdateTimeSeconds"], "r": c["newRating"], "contest": c["contestName"]} for c in history],
            "solved_histogram": analysis.solved_rating_histogram(solved),
            "tags": tags,
            "_solved_keys": keys,
        }

    def recommendations(profile: dict, n: int = 12) -> list[dict]:
        weak = [t["tag"] for t in profile["tags"][:5]]
        return recommend(app.state.store.problems, profile["_solved_keys"], weak, profile["level"], n=n)

    def public(profile: dict) -> dict:
        return {k: v for k, v in profile.items() if not k.startswith("_")}

    def problem_or_404(contest_id: int, index: str) -> dict:
        p = app.state.store.get(contest_id, index)
        if not p:
            raise HTTPException(404, "Problem not found")
        return p

    # ---------- pages ----------

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return page(request, "home.html")

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, cf: str = "", lc: str = ""):
        cf, lc = cf.strip(), lc.strip()
        ctx = {"cf_handle": cf, "lc_user": lc, "cf_error": None, "lc_error": None, "cf": None, "lc": None, "recs": []}
        if cf:
            try:
                prof = cf_profile(cf)
                ctx["cf"], ctx["recs"] = public(prof), recommendations(prof)
            except HTTPException as e:
                ctx["cf_error"] = e.detail
        if lc:
            try:
                ctx["lc"] = app.state.lc.profile(lc)
            except (LeetCodeError, Exception) as e:
                ctx["lc_error"] = str(e)
        return page(request, "profile.html", **ctx)

    @app.get("/compare", response_class=HTMLResponse)
    def compare_page(request: Request, a: str = "", b: str = ""):
        ctx = {"a": a, "b": b, "error": None, "pa": None, "pb": None, "winner": None}
        if a and b:
            try:
                pa, pb = public(cf_profile(a.strip())), public(cf_profile(b.strip()))
                ctx.update(pa=pa, pb=pb, winner=analysis.compare(pa["stats"], pb["stats"]))
            except HTTPException as e:
                ctx["error"] = e.detail
        return page(request, "compare.html", **ctx)

    @app.get("/problems", response_class=HTMLResponse)
    def problems_page(request: Request):
        store = app.state.store
        return page(request, "problems.html", names=[p["name"] for p in store.problems], tags=store.tags)

    @app.get("/problem/{contest_id}/{index}", response_class=HTMLResponse)
    def problem_page(request: Request, contest_id: int, index: str):
        p = problem_or_404(contest_id, index)
        return page(request, "problem.html", p=p, rating=effective_rating(p),
                    statement=app.state.store.statement(contest_id, index),
                    runner_on=app.state.runner_on, hints_on=app.state.hints.enabled, languages=LANGUAGES)

    @app.get("/predict", response_class=HTMLResponse)
    def predict_page(request: Request):
        tm, rm = app.state.tag_model, app.state.rating_model
        return page(request, "predict.html", tag_metrics=tm.metrics if tm else None,
                    rating_metrics=rm.metrics if rm else None)

    # ---------- JSON API ----------

    @app.get("/health")
    def health():
        st = app.state
        return {"ok": True, "problems": len(st.store.problems), "rating_model": st.rating_model is not None,
                "tag_model": st.tag_model is not None, "code_runner": st.runner_on, "ai_hints": st.hints.enabled}

    @app.get("/api/problems")
    def api_problems(name: str = "", tag: str = "", min_rating: int | None = None,
                     max_rating: int | None = None, limit: int = 200):
        return app.state.store.search(name, tag, min_rating, max_rating, min(limit, 1000))

    @app.get("/api/profile/{handle}")
    def api_profile(handle: str):
        return public(cf_profile(handle))

    @app.get("/api/recommend/{handle}")
    def api_recommend(handle: str, n: int = 12):
        return recommendations(cf_profile(handle), n=min(n, 50))

    @app.get("/api/leetcode/{username}")
    def api_leetcode(username: str):
        try:
            return app.state.lc.profile(username)
        except LeetCodeError as e:
            raise HTTPException(404, str(e))

    @app.get("/api/predict-rating/{contest_id}/{index}")
    def api_predict_rating(contest_id: int, index: str):
        p = problem_or_404(contest_id, index)
        if not app.state.rating_model:
            raise HTTPException(503, "Rating model not loaded")
        pred = app.state.rating_model.predict([p], app.state.store.problems)[0]
        return {"contest_id": contest_id, "index": p["index"], "official_rating": p["rating"], "predicted_rating": pred}

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

    @app.post("/api/hint")
    def api_hint(req: HintRequest, request: Request):
        p = problem_or_404(req.contest_id, req.index)
        if not app.state.limiter.allow(f"hint:{request.client.host if request.client else '?'}"):
            raise HTTPException(429, "Too many requests, wait a minute")
        try:
            text = app.state.hints.ask(req.mode, p["name"], app.state.store.statement(req.contest_id, req.index) or "", req.code)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            return JSONResponse({"response": f"AI error: {e}"}, status_code=502)
        return {"response": text}

    return app


app = create_app()
