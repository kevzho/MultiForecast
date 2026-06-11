import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.strengths import fit_strengths
from worldcup import strengths as strengths_module


def _match(date, home, away, home_score, away_score, neutral=True, tournament="FIFA World Cup"):
    return {
        "date": date,
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "neutral": neutral,
        "tournament": tournament,
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


def test_friendly_is_weighted_less_than_world_cup_match(monkeypatch):
    monkeypatch.setattr(
        strengths_module,
        "load_elo",
        lambda: {"Team A": 1600, "Team B": 1600},
    )
    matches = pd.DataFrame(
        [
            _match("2025-01-01", "Team A", "Team B", 3, 0, tournament="Friendly"),
            _match("2025-01-01", "Team A", "Team B", 3, 0, tournament="FIFA World Cup"),
        ]
    )
    matches = strengths_module._prepare_matches(matches, max_years=8)
    rows = strengths_module._goal_rows(matches, half_life_days=365)

    friendly_weight = rows.iloc[0]["weight"]
    world_cup_weight = rows.iloc[1]["weight"]

    assert friendly_weight < world_cup_weight
    assert np.isclose(friendly_weight / world_cup_weight, 0.4)


def test_opponent_normalization_rewards_identical_scoreline_vs_high_elo(monkeypatch):
    monkeypatch.setattr(
        strengths_module,
        "load_elo",
        lambda: {"Team A": 1600, "Elite": 1900, "Minnow": 1200},
    )
    common = [
        _match("2025-01-01", "Elite", "Minnow", 1, 1),
        _match("2025-02-01", "Minnow", "Elite", 1, 1),
        _match("2025-03-01", "Team A", "Elite", 1, 1),
        _match("2025-04-01", "Team A", "Minnow", 1, 1),
    ]
    high_elo_win = pd.DataFrame(
        common + [_match("2025-05-01", "Team A", "Elite", 3, 0)]
    )
    low_elo_win = pd.DataFrame(
        common + [_match("2025-05-01", "Team A", "Minnow", 3, 0)]
    )

    high_table = fit_strengths(high_elo_win, elo_shrinkage_alpha=0.0)
    low_table = fit_strengths(low_elo_win, elo_shrinkage_alpha=0.0)

    assert high_table.attack["Team A"] > low_table.attack["Team A"]


def test_global_elo_shrinkage_pulls_all_teams_toward_elo_implied(monkeypatch):
    monkeypatch.setattr(
        strengths_module,
        "load_elo",
        lambda: {"Team A": 1900, "Team B": 1500, "Team C": 1300},
    )
    history = pd.DataFrame(
        [
            _match("2025-01-01", "Team A", "Team B", 0, 3),
            _match("2025-02-01", "Team B", "Team A", 3, 0),
            _match("2025-03-01", "Team A", "Team C", 0, 2),
            _match("2025-04-01", "Team C", "Team A", 2, 0),
            _match("2025-05-01", "Team B", "Team C", 1, 1),
            _match("2025-06-01", "Team C", "Team B", 1, 1),
        ]
    )

    pure_fit = fit_strengths(history, elo_shrinkage_alpha=0.0)
    shrunk = fit_strengths(history, elo_shrinkage_alpha=0.5)
    elo_attack, elo_defense = strengths_module._elo_implied_strengths()

    for team in history["home_team"].unique():
        for pure_value, shrunk_value, elo_value in (
            (pure_fit.attack[team], shrunk.attack[team], elo_attack[team]),
            (pure_fit.defense[team], shrunk.defense[team], elo_defense[team]),
        ):
            low = min(pure_value, elo_value)
            high = max(pure_value, elo_value)
            if not np.isclose(pure_value, elo_value):
                assert low < shrunk_value < high


def test_half_life_365_weights_one_year_old_match_twice_two_year_old(monkeypatch):
    monkeypatch.setattr(
        strengths_module,
        "load_elo",
        lambda: {"Team A": 1600, "Team B": 1600},
    )
    matches = pd.DataFrame(
        [
            _match("2024-01-01", "Team A", "Team B", 2, 0),
            _match("2025-01-01", "Team A", "Team B", 2, 0),
            _match("2026-01-01", "Team A", "Team B", 2, 0),
        ]
    )
    matches = strengths_module._prepare_matches(matches, max_years=8)
    rows = strengths_module._goal_rows(matches, half_life_days=365)

    two_year_weight = rows.iloc[0]["weight"]
    one_year_weight = rows.iloc[1]["weight"]

    assert np.isclose(one_year_weight / two_year_weight, 2.0, rtol=0.01)
