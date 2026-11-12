"""Train the problem rating model and compare it with CFSeer's original approach.

    python -m scripts.train_rating

Evaluation holds out whole contests (GroupShuffleSplit): every problem from a
test contest is unseen in training. A random split lets the model learn from
other problems of the same contest, which flatters the score.
After evaluating, the final model is refit on all rated problems and saved.
"""
import json
import math

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit

from app import config
from app.ml.features import contest_stats, rating_features
from app.problems import join, load_raw


def gbm():
    return HistGradientBoostingRegressor(max_iter=600, learning_rate=0.05, random_state=0)


def score(y_true, y_pred):
    return {"mae": round(float(mean_absolute_error(y_true, y_pred)), 1),
            "within_100": round(float(np.mean(np.abs(y_pred - y_true) <= 100)), 3)}


def main():
    problems = join(*load_raw(config.DATA_DIR, None, max_age_hours=1e9))
    rated = [p for p in problems if p["rating"] is not None and p["solved_count"] > 0]
    tag_vocab = sorted({t for p in rated for t in p["tags"]})
    stats = contest_stats(problems)

    X = rating_features(rated, stats, tag_vocab)
    y = np.array([p["rating"] for p in rated], dtype=float)
    groups = np.array([p["contest_id"] for p in rated])
    tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=77).split(X, y, groups))

    # CFSeer's original model: linear regression on log(solves) + tags
    tag_cols = slice(X.shape[1] - len(tag_vocab), X.shape[1])
    base_X = np.hstack([X[:, [0]], X[:, tag_cols]])
    baseline = LinearRegression().fit(base_X[tr], y[tr])
    model = gbm().fit(X[tr], y[tr])

    metrics = {
        "split": "20% of contests held out",
        "n_train": int(len(tr)), "n_test": int(len(te)),
        "baseline_linear": score(y[te], baseline.predict(base_X[te])),
        "gradient_boosting": score(y[te], model.predict(X[te])),
    }
    b, g = metrics["baseline_linear"]["mae"], metrics["gradient_boosting"]["mae"]
    metrics["mae_reduction"] = round(1 - g / b, 3)
    print(json.dumps(metrics, indent=2))

    final = gbm().fit(X, y)
    config.MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": final, "tag_vocab": tag_vocab, "metrics": metrics}, config.MODELS_DIR / "rating.joblib", compress=3)
    print(f"Saved {config.MODELS_DIR / 'rating.joblib'}")


if __name__ == "__main__":
    main()
