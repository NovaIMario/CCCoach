"""Load the trained models and make predictions. Missing model files are not fatal:
the app still works, it just cannot predict."""
from pathlib import Path

import joblib
import numpy as np

from .features import clean_statement, contest_stats, rating_features


class RatingModel:
    def __init__(self, bundle: dict):
        self.model = bundle["model"]
        self.tag_vocab = bundle["tag_vocab"]
        self.metrics = bundle.get("metrics", {})

    def predict(self, problems: list[dict], all_problems: list[dict]) -> list[int]:
        """Predict ratings, rounded to the nearest 100 and clamped to Codeforces' 800-3500 range."""
        if not problems:
            return []
        X = rating_features(problems, contest_stats(all_problems), self.tag_vocab)
        raw = self.model.predict(X)
        return [int(np.clip(round(v / 100) * 100, 800, 3500)) for v in raw]


class TagModel:
    def __init__(self, bundle: dict):
        self.model = bundle["model"]
        self.vectorizer = bundle["vectorizer"]
        self.classes = list(bundle["classes"])
        self.threshold = bundle["threshold"]
        self.metrics = bundle.get("metrics", {})

    def predict(self, statement: str, top_k: int = 5) -> list[dict]:
        X = self.vectorizer.transform([clean_statement(statement)])
        probs = self.model.predict_proba(X)[0]
        order = np.argsort(probs)[::-1][:top_k]
        return [
            {"tag": self.classes[i], "confidence": round(float(probs[i]), 3), "predicted": bool(probs[i] >= self.threshold)}
            for i in order
        ]


def load_models(models_dir: Path) -> tuple[RatingModel | None, TagModel | None]:
    rating = tags = None
    if (models_dir / "rating.joblib").exists():
        rating = RatingModel(joblib.load(models_dir / "rating.joblib"))
    if (models_dir / "tags.joblib").exists():
        tags = TagModel(joblib.load(models_dir / "tags.joblib"))
    return rating, tags
