import numpy as np

from app.ml.features import clean_statement, contest_stats, division, letter_position, rating_features


def test_division():
    assert division("Codeforces Round 1000 (Div. 2)") == "div2"
    assert division("Codeforces Round 999 (Div. 1 + Div. 2)") == "div12"
    assert division("Educational Codeforces Round 170 (Rated for Div. 2)") == "edu"
    assert division("Codeforces Global Round 27") == "global"
    assert division("Kotlin Heroes") == "other"


def test_letter_position():
    assert letter_position("A") == (0, 0)
    assert letter_position("E2") == (4, 2)
    assert letter_position("f1") == (5, 1)
    assert letter_position("??") == (0, 0)


def test_rating_features_shape_and_values(problems):
    stats = contest_stats(problems)
    X = rating_features(problems[:5], stats, ["dp", "graphs"])
    assert X.shape == (5, 6 + 8 + 2)
    # problem A is the most-solved in its contest, so its relative solve feature is 0
    assert X[0, 4] == 0
    # problem D has both tags
    assert list(X[3, -2:]) == [1, 1]
    assert np.isclose(X[0, 0], np.log1p(20000))


def test_split_cf_header():
    from app.problems import split_cf_header
    limits, body = split_cf_header("C. MEX Cycle time limit per test 2 seconds memory limit per test 256 megabytes "
                                   "input standard input output standard output Evirir the dragon...")
    assert limits == "Time limit 2 seconds · Memory limit 256 megabytes"
    assert body == "Evirir the dragon..."
    assert split_cf_header("No header here") == (None, "No header here")


def test_clean_statement_drops_header_and_math():
    raw = ("C. Sum time limit per test 1 second memory limit per test 256 megabytes input standard input "
           "output standard output You are given $$$n$$$ numbers.")
    cleaned = clean_statement(raw)
    assert cleaned.startswith("You are given")
    assert "$$$" not in cleaned and "MATH" in cleaned
