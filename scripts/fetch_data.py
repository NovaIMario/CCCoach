"""Download the Codeforces problemset and contest list into data/.

    python -m scripts.fetch_data
"""
from app import config
from app.codeforces import CodeforcesClient
from app.problems import load_raw

if __name__ == "__main__":
    problemset, contests = load_raw(config.DATA_DIR, CodeforcesClient(), max_age_hours=0)
    print(f"Saved {len(problemset['problems'])} problems and {len(contests)} contests to {config.DATA_DIR}")
