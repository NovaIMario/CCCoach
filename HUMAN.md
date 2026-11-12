# CCCoach: how it works (for humans)

This file explains the project so you can find your way around, explain it in an interview, or change it.

## The big picture

```
            Codeforces API        LeetCode GraphQL        Gemini API
                  │                      │                     │
          codeforces.py            leetcode.py              ai.py
       (cache + rate limit)        (cache)            (fixed prompts, rate limit)
                  │                      │                     │
   problems.py ◄──┤                      │                     │
 (ProblemStore:   │                      │                     │
  ~11.5k problems │                      │                     │
  in memory)      │                      │                     │
       │          ▼                      ▼                     ▼
       │     analysis.py ──► recommend.py                      │
       │     (stats, weak tags)  (what to solve next)          │
       │                                                       │
       ├── ml/models.py (rating + tag models) ◄── ml/features.py ◄── scripts/train_*.py
       │                                                       │
       └──────────────────────► main.py ◄──────────────────────┘
                         (FastAPI: pages + JSON API)
                                   │
                    templates/*.html + static/*.js
                (Trie autocomplete, Monaco editor, Chart.js)
                                   │
                              runner.py
                    (compile/run C++ or Python with limits)
```

## What happens when you open a profile

1. `main.py` `/profile?cf=handle&lc=user` calls `cf_profile(handle)`.
2. That makes three Codeforces calls (user info, rating history, all submissions) through `CodeforcesClient`,
   which waits 2s between calls (the API allows about one call every 2 seconds) and caches results for 10 minutes.
3. `analysis.solved_keys` keeps accepted submissions only → a set of `(contest_id, index)`.
4. Those keys are looked up in the `ProblemStore` to get each solved problem's tags and rating.
5. `analysis.user_level` = current rating (or the median rating of solved problems if unrated).
6. `analysis.tag_profile` computes, for each tag: its share of all problems within ±300 of your level ("expected")
   and its share of your solves ("yours"). `weakness = expected / (yours + 0.01)`. Highest = weakest.
7. `recommend.recommend` takes the 5 weakest tags and scores every unsolved problem rated level..level+300:
   `score = sum of weak-tag weights − |rating − (level+100)| / 100`. Ties go to more-solved problems.
8. LeetCode stats come from one GraphQL query (`leetcode.py`).
9. The page is rendered with Jinja (auto-escaped, so problem names can't inject HTML). Charts are drawn by `static/charts.js`.

## The problem store (`problems.py`)

- On startup it loads `data/problemset.json` + `data/contests.json`, or downloads them if older than 24h.
- `join()` flattens the API response into one dict per problem and adds solve count, contest name/start and division.
- If `models/rating.joblib` exists, every **unrated** problem that has solves gets a `predicted_rating`.
  `effective_rating(p)` = official rating, else predicted. Search, weak tags and recommendations all use it.
- Optional `data/statements.json` (`"1316/B": "text..."`) shows statements and feeds the AI hints.

Search is a linear filter over ~11.5k dicts; that takes about a millisecond, so no database is needed.

## LeetCode (`lc_problems.py`, `leetcode.py`)

- **Problems:** on startup, LeetCode's GraphQL `questionList` (all problems, tags, Premium flag) and zerotrac's ratings
  (~2,600 contest problems) are downloaded and cached in `data/lc_raw.json`. Premium problems are dropped.
- **Rating:** CF rating = zerotrac rating − `LC_RATING_OFFSET` (600), rounded to 100, at least 800. Problems zerotrac
  doesn't rate get the median zerotrac rating of their difficulty, computed from the data, shown as "estimated".
- **Tags:** `LC_TO_CF_TAG` maps LeetCode tags to Codeforces tags (dynamic-programming → dp, union-find → dsu, ...).
  Generic tags (array, hash-table) have no equivalent and are only shown on the problem page.
- **Your history:** LeetCode publicly exposes per-tag solve counts and only the last 20 accepted problems. The tag
  counts are added to your Codeforces solves in the weak-tag analysis, but only for tags LeetCode can express;
  "constructive algorithms" etc. use Codeforces solves only, so they don't look weak just because LeetCode can't
  label them. The 20 recent problems are excluded from LeetCode recommendations.
- **Statements** are fetched on demand from LeetCode (HTML → plain text) and cached in memory.
- Everything LeetCode-related is optional: if LeetCode is unreachable, the app starts with Codeforces only.

## The models (`ml/`, `scripts/`)

**Shared features** (`ml/features.py`) are used by both training and the app, so they can't drift apart.

**Rating model** (`scripts/train_rating.py`) — `HistGradientBoostingRegressor` on:
- log(solve count), and log solves *minus* log solves of the contest's most-solved problem
  (so a Div. 1 and a Div. 4 problem with the same raw solve count aren't treated alike)
- problem letter (A=0, B=1, …) and sub-index (E1/E2), number of problems in the contest
- contest division (one-hot), contest start time (Codeforces has grown, so raw solve counts inflate over time)
- tags (multi-hot)

**Tag model** (`scripts/train_tags.py`) — TF-IDF (30k uni/bi-grams) → one logistic regression per tag.
A tag is predicted when its probability ≥ a threshold picked on part of the training set (0.225).
The default 0.5 was far too strict for rare tags, which is why the original model missed so many.

**Evaluation**: `GroupShuffleSplit` by contest. All problems of a test contest are unseen. Both scripts also
train the original CFSeer setup on the same split, so the comparison is fair. Final models are refit on all data.

## The code runner (`runner.py`)

Each run: new temp dir → (C++) `g++ -O2 -std=c++17` with a 15s compile limit → run with stdin, 2s wall limit →
delete the dir. On Linux the child process also gets `setrlimit` limits (CPU seconds, 256 MB memory, output file size,
max 64 processes) and its own session. The environment is replaced with a minimal one, so `GEMINI_API_KEY`
is not visible to user code (there's a test for that). Output is cut at 64 KB.

Honest limitation: this is resource limiting, not isolation. For a public server, use the Docker image (non-root user)
or turn the runner off with `ENABLE_CODE_RUNNER=0`.

## AI hints (`ai.py`)

Three fixed modes: `hint` (one nudge, no code), `review` (bugs in your code), `solution` (full explanation + C++).
Gemini models are often overloaded (503) or hang until a 504, so each model gets 25s and then the next model in
`FALLBACK_MODELS` is tried (the Flash-Lite models are rarely busy). A 404 (model retired for this key) also moves on.
The prompt includes the statement (if available) and your editor contents. There is no free-text mode, so the
server's API key can't be used as a general chatbot. 10 requests/minute per IP.

## Frontend (`app/static`)

- `trie.js` — the AlgoReady Trie, improved: inserts every word of a name (so "tree" finds "Game on Growing Tree"),
  and caps stored names per node at 50 so memory stays bounded.
- `problems.js` — search page; builds DOM with `textContent` (never `innerHTML`) for data from Codeforces.
- `problem.js` — Monaco editor (code saved per problem in `localStorage`), run button, AI buttons, MathJax for `$$$…$$$` maths.
- `charts.js` — rating history and solved-rating histogram (Chart.js).

## Tests (`tests/`)

48 tests, no network: `conftest.py` builds a 200-problem fake problemset and fake Codeforces/LeetCode/Gemini clients,
then `create_app(...)` is given those fakes. Covered: stats, weak tags, recommendations, features, runner limits and
secrets, every page renders, HTML escaping, API errors (unknown handle → 404, bad language → 400).
CI (`.github/workflows/ci.yml`) runs the tests, then builds the Docker image and checks `/health`.

## File map

| Path | What |
|---|---|
| `app/main.py` | FastAPI app factory, all routes |
| `app/config.py` | Settings from env / `.env` |
| `app/codeforces.py`, `app/leetcode.py` | API clients |
| `app/problems.py` | Problem store, search |
| `app/analysis.py` | Rating stats, weak tags |
| `app/recommend.py` | Recommendations |
| `app/ml/features.py`, `app/ml/models.py` | Features, model loading/prediction |
| `app/runner.py` | Code execution |
| `app/ai.py` | Gemini hints, rate limiter |
| `scripts/` | Data download, statement import, training |
| `models/` | Trained models (committed, so deploys work without training) |
| `data/` | Downloaded data (git-ignored) |

## Ideas for later

- Track recommendations you solved and adapt (spaced repetition for tags).
- Map LeetCode problems to Codeforces tags so LeetCode history also feeds the weak-tag analysis.
- Run code in a real sandbox (e.g. nsjail or a separate judge service).
