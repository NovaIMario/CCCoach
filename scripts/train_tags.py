"""Train the tag classifier (problem statement -> tags) and compare with CFSeer's original.

    python -m scripts.train_tags

Needs data/statements.json (see scripts/import_statements.py) and data/problemset.json.
Like the rating model, it is evaluated on held-out contests, and the decision
threshold is chosen on a slice of the training data, never on the test set.
"""
import json

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from app import config
from app.ml.features import clean_statement
from app.problems import join, load_raw

THRESHOLDS = np.arange(0.05, 0.6, 0.025)


def vectorizer():
    return TfidfVectorizer(max_features=30000, ngram_range=(1, 2), stop_words="english", min_df=2, sublinear_tf=True)


def classifier():
    return OneVsRestClassifier(LogisticRegression(max_iter=2000, C=4.0), n_jobs=-1)


def f1s(Y, P):
    return {"micro_f1": round(float(f1_score(Y, P, average="micro", zero_division=0)), 3),
            "macro_f1": round(float(f1_score(Y, P, average="macro", zero_division=0)), 3)}


def pick_threshold(texts, Y, idx):
    a, b = train_test_split(idx, test_size=0.2, random_state=1)
    vec = vectorizer()
    m = classifier().fit(vec.fit_transform([texts[i] for i in a]), Y[a])
    probs = m.predict_proba(vec.transform([texts[i] for i in b]))
    return float(max(THRESHOLDS, key=lambda t: f1_score(Y[b], probs >= t, average="micro", zero_division=0)))


def main():
    statements = json.loads((config.DATA_DIR / "statements.json").read_text(encoding="utf-8"))
    problems = join(*load_raw(config.DATA_DIR, None, max_age_hours=1e9))
    rows = [(p, statements[k]) for p in problems if p["tags"] and (k := f"{p['contest_id']}/{p['index']}") in statements]
    raw = [s for _, s in rows]
    texts = [clean_statement(s) for s in raw]
    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform([p["tags"] for p, _ in rows])
    groups = np.array([p["contest_id"] for p, _ in rows])
    tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=77).split(texts, Y, groups))
    print(f"{len(rows)} problems with statements, {len(mlb.classes_)} tags")

    # CFSeer's original setup: 2k features, raw text, default 0.5 threshold
    v0 = TfidfVectorizer(max_features=2000, ngram_range=(1, 2), stop_words="english", min_df=5)
    m0 = OneVsRestClassifier(LogisticRegression(max_iter=1000), n_jobs=-1).fit(v0.fit_transform([raw[i] for i in tr]), Y[tr])
    baseline = f1s(Y[te], m0.predict(v0.transform([raw[i] for i in te])))

    threshold = pick_threshold(texts, Y, tr)
    vec = vectorizer()
    m = classifier().fit(vec.fit_transform([texts[i] for i in tr]), Y[tr])
    improved = f1s(Y[te], m.predict_proba(vec.transform([texts[i] for i in te])) >= threshold)

    metrics = {"split": "20% of contests held out", "n_train": int(len(tr)), "n_test": int(len(te)),
               "baseline": baseline, "improved": improved, "threshold": round(threshold, 3),
               "micro_f1_gain": round(improved["micro_f1"] / baseline["micro_f1"] - 1, 3)}
    print(json.dumps(metrics, indent=2))

    vec = vectorizer()
    final = classifier().fit(vec.fit_transform(texts), Y)
    config.MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump({"model": final, "vectorizer": vec, "classes": list(mlb.classes_), "threshold": threshold,
                 "metrics": metrics}, config.MODELS_DIR / "tags.joblib", compress=3)
    print(f"Saved {config.MODELS_DIR / 'tags.joblib'}")


if __name__ == "__main__":
    main()
