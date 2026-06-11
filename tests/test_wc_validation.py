import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.model import ScorelineDist
from worldcup.validation import backtest


class CoinFlipModel:
    def predict(self, home, away, *, neutral=False):
        grid = np.zeros((11, 11))
        grid[1, 0] = 1 / 3
        grid[1, 1] = 1 / 3
        grid[0, 1] = 1 / 3
        return ScorelineDist(grid)


class PerfectModel:
    def __init__(self, outcomes):
        self.outcomes = outcomes

    def predict(self, home, away, *, neutral=False):
        grid = np.zeros((11, 11))
        outcome = self.outcomes[(home, away)]
        if outcome == "home":
            grid[1, 0] = 1.0
        elif outcome == "away":
            grid[0, 1] = 1.0
        else:
            grid[1, 1] = 1.0
        return ScorelineDist(grid)


def _history():
    return pd.DataFrame(
        [
            {
                "date": "2020-01-01",
                "home_team": "A",
                "away_team": "B",
                "home_score": 2,
                "away_score": 0,
                "neutral": True,
            },
            {
                "date": "2020-02-01",
                "home_team": "B",
                "away_team": "C",
                "home_score": 1,
                "away_score": 1,
                "neutral": True,
            },
            {
                "date": "2020-03-01",
                "home_team": "C",
                "away_team": "A",
                "home_score": 0,
                "away_score": 3,
                "neutral": True,
            },
        ]
    )


def test_backtest_metrics_are_finite_and_in_valid_ranges():
    metrics = backtest(lambda: CoinFlipModel(), _history(), since="2018-01-01")

    assert np.isfinite(metrics["logloss"])
    assert 0 <= metrics["brier"] <= 2
    assert 0 <= metrics["rps"] <= 1
    assert metrics["calibration_bins"]
    for row in metrics["calibration_bins"]:
        assert 0 <= row["mean_confidence"] <= 1
        assert 0 <= row["observed_frequency"] <= 1
        assert row["n"] > 0


def test_perfect_prediction_scores_better_than_coin_flip():
    outcomes = {
        ("A", "B"): "home",
        ("B", "C"): "draw",
        ("C", "A"): "away",
    }
    perfect = backtest(lambda: PerfectModel(outcomes), _history(), since="2018-01-01")
    coin = backtest(lambda: CoinFlipModel(), _history(), since="2018-01-01")

    assert perfect["logloss"] < coin["logloss"]
    assert perfect["brier"] < coin["brier"]
    assert perfect["rps"] < coin["rps"]
