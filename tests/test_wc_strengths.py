import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.strengths import fit_strengths


def _match(date, home, away, home_score, away_score, neutral=True):
    return {
        "date": date,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "neutral": neutral,
    }


def test_heavy_scoring_team_has_above_median_attack_and_centered_strengths():
    history = pd.DataFrame(
        [
            _match("2025-01-01", "Team A", "Team B", 4, 0),
            _match("2025-02-01", "Team A", "Team C", 5, 1),
            _match("2025-03-01", "Team B", "Team A", 1, 3),
            _match("2025-04-01", "Team C", "Team A", 0, 4),
            _match("2025-05-01", "Team B", "Team C", 1, 1),
            _match("2025-06-01", "Team C", "Team B", 1, 0),
        ]
    )

    table = fit_strengths(history)

    median_attack = float(np.median(list(table.attack.values())))
    assert table.attack["Team A"] > median_attack
    assert abs(np.mean(list(table.attack.values()))) < 1e-10
    assert abs(np.mean(list(table.defense.values()))) < 1e-10


def test_expected_goals_are_positive_and_finite_for_known_teams():
    history = pd.DataFrame(
        [
            _match("2025-01-01", "Spain", "France", 2, 1),
            _match("2025-02-01", "France", "Spain", 1, 1),
            _match("2025-03-01", "Spain", "Germany", 3, 0),
            _match("2025-04-01", "Germany", "France", 0, 2),
        ]
    )

    table = fit_strengths(history)
    lam_h, lam_a = table.expected_goals("Spain", "France", neutral=True)

    assert lam_h > 0
    assert lam_a > 0
    assert math.isfinite(lam_h)
    assert math.isfinite(lam_a)


def test_recent_blowout_moves_strength_more_than_old_blowout():
    base_matches = [
        _match("2024-01-01", "Team A", "Team B", 1, 1),
        _match("2024-02-01", "Team B", "Team A", 1, 1),
        _match("2024-03-01", "Team A", "Team C", 1, 1),
        _match("2024-04-01", "Team C", "Team A", 1, 1),
        _match("2024-05-01", "Team B", "Team C", 1, 1),
        _match("2024-06-01", "Team C", "Team B", 1, 1),
    ]
    old_history = pd.DataFrame(
        base_matches + [_match("2015-01-01", "Team A", "Team B", 6, 0)]
    )
    recent_history = pd.DataFrame(
        base_matches + [_match("2025-01-01", "Team A", "Team B", 6, 0)]
    )

    old_table = fit_strengths(old_history, max_years=12)
    recent_table = fit_strengths(recent_history, max_years=12)

    assert recent_table.attack["Team A"] > old_table.attack["Team A"]
