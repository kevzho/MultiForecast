import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.model import EloModel, ScorelineDist
from worldcup.models import AVAILABLE_MODELS
from worldcup.models.bradley_terry import BradleyTerryModel, DavidsonParams
from worldcup.models.dixon_coles import DixonColesModel
from worldcup.models.poisson import PoissonModel
from worldcup.models.skellam import skellam_wdl
from worldcup.simulate import simulate_tournament
from worldcup.strengths import StrengthTable


def _strength_table() -> StrengthTable:
    teams = [f"{group}{idx}" for group in "AB" for idx in range(1, 5)]
    attack = {
        team: (4 - idx) * 0.18
        for group in "AB"
        for idx, team in enumerate([f"{group}{i}" for i in range(1, 5)], start=1)
    }
    defense = {
        team: (idx - 2.5) * 0.08
        for group in "AB"
        for idx, team in enumerate([f"{group}{i}" for i in range(1, 5)], start=1)
    }
    return StrengthTable(attack, defense, base_rate=0.1, home_adv=0.12)


def _models():
    strengths = _strength_table()
    bt_strengths = {
        "A1": 1.0,
        "A2": 0.5,
        "A3": 0.0,
        "A4": -0.5,
        "B1": 0.8,
        "B2": 0.3,
        "B3": -0.2,
        "B4": -0.7,
    }
    elo = {team: 1600 + 100 * value for team, value in bt_strengths.items()}
    return [
        EloModel(elo),
        PoissonModel(strengths),
        DixonColesModel(strengths, rho=-0.13),
        BradleyTerryModel(strengths, DavidsonParams(bt_strengths, draw=0.7)),
    ]


def _two_group_fixture_data():
    groups = {group: [f"{group}{idx}" for idx in range(1, 5)] for group in "AB"}
    groups_df = pd.DataFrame(
        [
            {
                "Group": group,
                "Team": team,
                "FIFA_Rank": group_idx * 4 + team_idx,
                "Confederation": "TEST",
            }
            for group_idx, (group, teams) in enumerate(groups.items())
            for team_idx, team in enumerate(teams, start=1)
        ]
    )
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
    fixtures_df = pd.DataFrame(rows)
    results_df = pd.DataFrame(columns=["MatchID", "FTHG", "FTAG"])
    fifa_ranks = dict(zip(groups_df["Team"], groups_df["FIFA_Rank"]))
    return groups_df, fixtures_df, results_df, fifa_ranks


def test_registry_exposes_four_selectable_models():
    assert set(AVAILABLE_MODELS) == {
        "Elo-Poisson",
        "Data Poisson",
        "Dixon-Coles",
        "Bradley-Terry",
    }


def test_every_model_returns_valid_scoreline_dist():
    for model in _models():
        for home, away in [("A1", "A2"), ("A4", "B1"), ("B2", "A3")]:
            dist = model.predict(home, away, neutral=True)
            assert isinstance(dist, ScorelineDist)
            assert dist.grid.shape == (11, 11)
            assert np.isclose(dist.grid.sum(), 1)
            assert all(0 <= prob <= 1 for prob in dist.wdl)


def test_skellam_wdl_matches_grid_summed_poisson():
    model = PoissonModel(_strength_table())
    dist = model.predict("A1", "B2", neutral=True)
    lam_h, lam_a = model.expected_goals("A1", "B2", neutral=True)

    assert np.allclose(skellam_wdl(lam_h, lam_a), dist.wdl, atol=1e-3)
    assert np.allclose(model.wdl_fast("A1", "B2", neutral=True), dist.wdl, atol=1e-3)


def test_negative_rho_dixon_coles_moves_low_score_cells_expected_way():
    strengths = _strength_table()
    poisson = PoissonModel(strengths).predict("A1", "B2", neutral=True).grid
    dixon_coles = DixonColesModel(strengths, rho=-0.13).predict(
        "A1",
        "B2",
        neutral=True,
    ).grid

    assert dixon_coles[0, 0] > poisson[0, 0]
    assert dixon_coles[1, 1] > poisson[1, 1]
    assert dixon_coles[0, 1] < poisson[0, 1]
    assert dixon_coles[1, 0] < poisson[1, 0]


def test_bradley_terry_strength_and_equal_strength_symmetry():
    strengths = _strength_table()
    model = BradleyTerryModel(
        strengths,
        DavidsonParams({"Strong": 1.0, "Weak": -1.0, "EvenA": 0.25, "EvenB": 0.25}, 0.7),
    )

    p_home, _, p_away = model.wdl("Strong", "Weak", neutral=True)
    assert p_home > p_away

    p_even_home, _, p_even_away = model.wdl("EvenA", "EvenB", neutral=True)
    assert np.isclose(p_even_home, p_even_away)


def test_all_models_run_through_two_group_simulation(tmp_path, monkeypatch):
    import worldcup.simulate as simulate_module

    monkeypatch.setattr(simulate_module, "CACHE_PATH", tmp_path / "wc_simulations.json")
    groups_df, fixtures_df, results_df, fifa_ranks = _two_group_fixture_data()

    for model in _models():
        result = simulate_tournament(
            model,
            groups_df,
            fixtures_df,
            results_df,
            fifa_ranks,
            n_sims=3,
            seed=2026,
            shootout="coin",
            elo={team: 1600 for team in groups_df["Team"]},
        )

        assert set(result["per_team"]) == set(groups_df["Team"])
        assert set(result["per_group"]) == {"A", "B"}
        assert sum(team["P(advance)"] for team in result["per_team"].values()) == 4
