# CCCoach

A training coach for competitive programmers. It reads your **Codeforces** and **LeetCode** history,
finds the topics you under-practise for your rating, recommends the next problems to solve, and lets you
solve them in the browser with a code editor, a code runner and AI hints.

CCCoach merges three earlier projects into one app:

| Earlier project | What it did | What CCCoach adds |
|---|---|---|
| **CF Analysis** | Rating history, solved-tag counts, compare two users | Weak tags relative to your level, LeetCode stats, recommendations |
| **AlgoReady** | Problem search with Trie autocomplete, Monaco editor, Gemini hints | Word-level autocomplete, C++ **and** Python, resource-limited runner, fixed AI prompt types |
| **CFSeer** | Rating predictor (MAE 212.8), tag predictor (micro-F1 0.297) | Retrained models: **MAE 119.8** and **micro-F1 0.472** on held-out contests |

## Results

Both models are evaluated on **contests the model never saw** (20% of contests held out), which is stricter
than a random split because problems from the same contest are correlated.

| Model | Original (CFSeer approach) | CCCoach | Change |
|---|---|---|---|
| Rating predictor, MAE | 226.4 | **119.8** | −47% |
| Rating predictor, within ±100 | 28.6% | **53.8%** | ×1.9 |
| Tag predictor, micro-F1 | 0.294 | **0.472** | +60% |
| Tag predictor, macro-F1 | 0.169 | **0.298** | +76% |

*(The original CFSeer reported MAE 212.8 on a random split of older data; re-run on today's data with a contest split it scores 226.4.)*

What made the difference:
- **Rating:** the problem's letter (A, B, C…), the contest division and solve counts *relative to the contest's
  easiest problem* matter more than raw solve counts. Gradient boosting captures how they interact.
- **Tags:** removing the "C. Name time limit… standard output" header from statements, a larger TF-IDF vocabulary,
  and choosing the decision threshold (0.225 instead of 0.5) on training data.

## Features

- **Profile** — rating history chart, solved-by-rating histogram, LeetCode solved counts and contest rating.
- **Weak tags** — compares each tag's share of what you solved with its share of problems around your rating.
- **Recommendations** — unsolved Codeforces *and* LeetCode problems in your weakest tags, 0–300 above your level.
- **LeetCode problems on the Codeforces scale** — ~3,300 free LeetCode problems, rated with zerotrac's contest ratings
  converted as CF ≈ LC − 600 (configurable with `LC_RATING_OFFSET`); unrated ones get the median rating of their
  difficulty. LeetCode tags are mapped to Codeforces tags, and your LeetCode per-tag solve counts feed the weak-tag analysis.
- **Problem search** — Trie autocomplete on any word of the name, filter by tag and rating (predicted ratings for unrated problems).
- **Solve page** — statement with maths, Monaco editor (C++17 / Python 3), run against custom input, AI hint / code review / solution.
  When a Gemini model is overloaded, the coach falls back to lighter models instead of failing.
- **Compare** — two Codeforces users side by side.
- **Models page** — metrics and a live tag predictor.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env              # optional: add GEMINI_API_KEY for AI hints
uvicorn app.main:app --reload     # downloads the problemset on first start
```
Open http://127.0.0.1:8000.

Optional: problem statements on the solve page (and needed to retrain the tag model):
```bash
python -m scripts.import_statements path/to/problems.json
```

Retrain the models:
```bash
python -m scripts.fetch_data
python -m scripts.train_rating
python -m scripts.train_tags      # needs data/statements.json
```

Tests (no network, no secrets):
```bash
CCCOACH_OFFLINE=1 pytest -q
```

Docker:
```bash
docker build -t cccoach . && docker run -p 8000:8000 cccoach
```

## Security notes

The code runner executes untrusted code. It uses a fresh temp directory, a 2s timeout, a clean environment (no API keys),
and on Linux CPU/memory/file-size/process limits. It is not a full sandbox, so public deployments should use the Docker image
(non-root user) or set `ENABLE_CODE_RUNNER=0`. AI requests and runs are rate-limited per IP.

See [HUMAN.md](HUMAN.md) for the architecture.
