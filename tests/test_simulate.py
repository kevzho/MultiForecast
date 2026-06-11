import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.model import ScorelineDist
from worldcup.simulate import simulate_tournament


class StubModel:
    def __init__(self, strengths):
        self.strengths = strengths

    def predict(self, home, away, *, neutral=False):
        grid = np.zeros((11, 11))
        if self.strengths[home] > self.strengths[away]:
            grid[2, 0] = 1.0
        elif self.strengths[home] < self.strengths[away]:
            grid[0, 2] = 1.0
        else:
            grid[1, 1] = 1.0
        return ScorelineDist(grid)


class CountingProbModel:
    def __init__(self, strengths):
        self.strengths = strengths
        self.predict_calls = 0

    def predict(self, home, away, *, neutral=False):
        self.predict_calls += 1
        grid = np.zeros((11, 11))
        if self.strengths[home] >= self.strengths[away]:
            grid[2, 0] = 0.65
            grid[1, 1] = 0.20
            grid[0, 2] = 0.15
        else:
            grid[2, 0] = 0.15
            grid[1, 1] = 0.20
            grid[0, 2] = 0.65
        return ScorelineDist(grid)


def _fixture_rows(groups):
    rows = []
    match_id = 1
    for group, teams in groups.items():
        for i, home in enumerate(teams):
            for away in teams[i + 1 :]:
                rows.append(
                    {
                        "MatchID": match_id,
                        "Date": "2026-06-11",
                        "Stage": "Group",
                        "Group": group,
                        "HomeTeam": home,
                        "AwayTeam": away,
                        "Venue": "TBD",
                        "Neutral": True,
                    }
                )
                match_id += 1
    return rows


def _world_cup_fixture_data():
    groups = {
        group: [f"{group}{idx}" for idx in range(1, 5)]
        for group in "ABCDEFGHIJKL"
    }
    groups_df = pd.DataFrame(
        [
            {
                "Group": group,
                "Team": team,
                "FIFA_Rank": int(group_idx * 4 + team_idx),
                "Confederation": "TEST",
            }
            for group_idx, (group, teams) in enumerate(groups.items())
            for team_idx, team in enumerate(teams, start=1)
        ]
    )
    fixtures_df = pd.DataFrame(_fixture_rows(groups))
    results_df = pd.DataFrame(columns=["MatchID", "FTHG", "FTAG"])
    fifa_ranks = dict(zip(groups_df["Team"], groups_df["FIFA_Rank"]))
    strengths = {team: 1000 - rank for team, rank in fifa_ranks.items()}
    return groups_df, fixtures_df, results_df, fifa_ranks, strengths


def test_simulate_probabilities_and_group_counts_are_sensible(tmp_path, monkeypatch):
    import worldcup.simulate as simulate_module

    monkeypatch.setattr(simulate_module, "CACHE_PATH", tmp_path / "wc_simulations.json")
    groups_df, fixtures_df, results_df, fifa_ranks, strengths = _world_cup_fixture_data()

    result = simulate_tournament(
        StubModel(strengths),
        groups_df,
        fixtures_df,
        results_df,
        fifa_ranks,
        n_sims=20,
        seed=2026,
        shootout="coin",
        elo=strengths,
    )

    for team_result in result["per_team"].values():
        for key, value in team_result.items():
            if key.startswith("P("):
                assert 0 <= value <= 1
        assert set(team_result["finish_distribution"]) == {"1st", "2nd", "3rd", "4th"}

    for matrix in result["per_group"].values():
        assert len(matrix) == 4
        for team, position_probs in matrix.items():
            assert len(position_probs) == 4
            assert all(0 <= prob <= 1 for prob in position_probs.values())
            assert np.isclose(sum(position_probs.values()), 1)

    assert sum(team["P(advance)"] for team in result["per_team"].values()) == 32


def test_dominant_team_has_highest_win_cup_probability(tmp_path, monkeypatch):
    import worldcup.simulate as simulate_module

    monkeypatch.setattr(simulate_module, "CACHE_PATH", tmp_path / "wc_simulations.json")
    groups_df, fixtures_df, results_df, fifa_ranks, strengths = _world_cup_fixture_data()
    strengths["A1"] = 5000

    result = simulate_tournament(
        StubModel(strengths),
        groups_df,
        fixtures_df,
        results_df,
        fifa_ranks,
        n_sims=30,
        seed=7,
        shootout="coin",
        elo=strengths,
    )

    win_probs = {
        team: stats["P(win_cup)"] for team, stats in result["per_team"].items()
    }

    assert max(win_probs, key=win_probs.get) == "A1"


def test_predict_memoization_preserves_seeded_results_and_reduces_calls(tmp_path, monkeypatch):
    import worldcup.simulate as simulate_module

    groups_df, fixtures_df, results_df, fifa_ranks, strengths = _world_cup_fixture_data()

    monkeypatch.setattr(simulate_module, "CACHE_PATH", tmp_path / "memoized.json")
    memoized_model = CountingProbModel(strengths)
    memoized = simulate_tournament(
        memoized_model,
        groups_df,
        fixtures_df,
        results_df,
        fifa_ranks,
        n_sims=5,
        seed=99,
        shootout="coin",
        elo=strengths,
        force=True,
        memoize_predictions=True,
    )

    monkeypatch.setattr(simulate_module, "CACHE_PATH", tmp_path / "unmemoized.json")
    unmemoized_model = CountingProbModel(strengths)
    unmemoized = simulate_tournament(
        unmemoized_model,
        groups_df,
        fixtures_df,
        results_df,
        fifa_ranks,
        n_sims=5,
        seed=99,
        shootout="coin",
        elo=strengths,
        force=True,
        memoize_predictions=False,
    )

    assert memoized == unmemoized
    assert memoized_model.predict_calls < unmemoized_model.predict_calls
