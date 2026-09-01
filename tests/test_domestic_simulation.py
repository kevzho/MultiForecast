from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domestic.artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    artifact_envelope,
    match_breakdown_artifact,
    read_json_artifact,
    season_forecast_artifact,
    vercel_response,
    write_json_artifact,
)
from domestic.breakdowns import build_match_breakdown
from domestic.simulation import simulate_fixture_outcomes, simulate_season
from domestic.standings import build_table, empty_table, rank_table


@dataclass(frozen=True)
class GridDistribution:
    grid: np.ndarray


class GridModel:
    name = "test_scoreline"

    def __init__(self, grid: np.ndarray, ratings=None):
        self.grid = grid
        self.ratings = ratings or {}
        self.predict_calls = 0

    def predict(self, home, away, *, neutral=False):
        self.predict_calls += 1
        return GridDistribution(self.grid)


@dataclass(frozen=True)
class LeagueStub:
    slug: str
    season: str
    team_count: int
    points_for_win: int = 3
    standings_tiebreakers: tuple[str, ...] = (
        "points",
        "goal_difference",
        "goals_for",
    )
    champions_league_positions: tuple[int, ...] = (1, 2, 3, 4)
    europa_league_positions: tuple[int, ...] = (5,)
    conference_league_positions: tuple[int, ...] = (6,)
    relegation_positions: tuple[int, ...] = ()
    relegation_playoff_positions: tuple[int, ...] = ()


def _grid(*entries):
    grid = np.zeros((6, 6), dtype=float)
    for home_goals, away_goals, probability in entries:
        grid[home_goals, away_goals] = probability
    return grid


def test_build_table_tracks_scores_points_and_form():
    results = [
        {"home_team": "Alpha", "away_team": "Bravo", "home_goals": 2, "away_goals": 0},
        {"home_team": "Charlie", "away_team": "Alpha", "home_goals": 1, "away_goals": 1},
        {"home_team": "Bravo", "away_team": "Charlie", "home_goals": None, "away_goals": None},
    ]

    table = build_table(results, teams=("Alpha", "Bravo", "Charlie"))

    assert table["Alpha"].played == 2
    assert table["Alpha"].points == 4
    assert table["Alpha"].goals_for == 3
    assert table["Alpha"].goals_against == 1
    assert table["Alpha"].goal_difference == 2
    assert table["Alpha"].form == ["W", "D"]
    assert table["Bravo"].points == 0


def test_rank_table_uses_configured_head_to_head_before_goal_difference():
    table = empty_table(("Alpha", "Bravo"))
    table["Alpha"].points = 40
    table["Alpha"].goals_for = 30
    table["Alpha"].goals_against = 25
    table["Bravo"].points = 40
    table["Bravo"].goals_for = 40
    table["Bravo"].goals_against = 20
    meetings = [
        {"home_team": "Alpha", "away_team": "Bravo", "home_goals": 1, "away_goals": 0},
        {"home_team": "Bravo", "away_team": "Alpha", "home_goals": 1, "away_goals": 1},
    ]

    h2h_ranked = rank_table(
        table,
        ("points", "head_to_head_points", "goal_difference"),
        results=meetings,
    )
    goal_difference_ranked = rank_table(table, ("points", "goal_difference"))

    assert [row.team for row in h2h_ranked] == ["Alpha", "Bravo"]
    assert [row.team for row in goal_difference_ranked] == ["Bravo", "Alpha"]


@pytest.mark.parametrize("team_count", (18, 20))
def test_simulation_supports_dynamic_league_sizes_and_slot_rules(team_count):
    teams = [f"Team {index:02d}" for index in range(team_count)]
    fixtures = [
        {"home_team": teams[0], "away_team": teams[1], "home_goals": None, "away_goals": None},
        {"home_team": teams[2], "away_team": teams[3], "home_goals": 1, "away_goals": 0},
    ]
    config = LeagueStub(
        slug=f"league_{team_count}",
        season="2627",
        team_count=team_count,
        relegation_positions=tuple(range(team_count - 1, team_count + 1)),
        relegation_playoff_positions=(team_count - 2,),
    )
    model = GridModel(_grid((2, 0, 1.0)))

    forecast = simulate_season(
        fixtures,
        model,
        teams=teams,
        league_config=config,
        n_simulations=8,
        seed=2627,
    )

    assert forecast.team_count == team_count
    assert forecast.remaining_fixtures == 1
    assert model.predict_calls == 1
    assert len(forecast.teams[teams[0]].position_probabilities) == team_count
    assert forecast.teams[teams[0]].expected_goals_for == 2
    assert forecast.teams[teams[0]].expected_goals_against == 0
    assert forecast.teams[teams[2]].expected_points == 3
    assert sum(item.title_probability for item in forecast.teams.values()) == 1
    assert sum(
        item.qualification_probabilities["champions_league"]
        for item in forecast.teams.values()
    ) == 4
    assert sum(item.relegation_probability for item in forecast.teams.values()) == 2
    for item in forecast.teams.values():
        assert np.isclose(sum(item.position_probabilities), 1)


def test_simulation_is_seeded_and_samples_scorelines():
    teams = [f"Club {index}" for index in range(4)]
    fixtures = [
        {"home_team": "Club 0", "away_team": "Club 1"},
        {"home_team": "Club 2", "away_team": "Club 3"},
    ]
    model = GridModel(_grid((3, 1, 0.55), (0, 2, 0.45)))
    options = {
        "teams": teams,
        "n_simulations": 60,
        "seed": 99,
        "qualification_slots": {"continental": (1, 2)},
        "relegation_slots": 1,
    }

    first = simulate_season(fixtures, model, **options)
    second = simulate_season(fixtures, GridModel(model.grid), **options)

    assert first.to_dict() == second.to_dict()
    assert first.relegation_positions == (4,)
    assert first.qualification_positions == {"continental": (1, 2)}
    assert first.teams["Club 0"].expected_goals_for > 0
    assert first.teams["Club 0"].expected_goals_against > 0


def test_fixture_outcomes_create_conditional_season_forecasts():
    fixture = {"home_team": "Alpha", "away_team": "Bravo"}
    model = GridModel(_grid((2, 0, 0.4), (1, 1, 0.3), (0, 1, 0.3)))

    outcomes = simulate_fixture_outcomes(
        [fixture],
        fixture,
        model,
        teams=("Alpha", "Bravo"),
        n_sims=4,
        seed=7,
        relegation_slots=(2,),
    )

    assert set(outcomes) == {"home_win", "draw", "away_win"}
    assert outcomes["home_win"].teams["Alpha"].title_probability == 1
    assert outcomes["away_win"].teams["Bravo"].title_probability == 1
    assert outcomes["draw"].teams["Alpha"].expected_points == 1


def test_match_breakdown_contains_markets_comparison_form_and_season_swing():
    primary = GridModel(
        _grid((2, 0, 0.4), (1, 1, 0.3), (0, 1, 0.2), (3, 1, 0.1)),
        ratings={"Home": 1700, "Away": 1600},
    )
    comparison = GridModel(_grid((1, 0, 0.6), (0, 0, 0.25), (0, 1, 0.15)))
    results = [
        {"home_team": "Home", "away_team": "Third", "home_goals": 2, "away_goals": 0},
        {"home_team": "Third", "away_team": "Away", "home_goals": 1, "away_goals": 1},
    ]
    baseline = {
        "teams": {
            "Home": {"expected_points": 77, "title_probability": 0.4},
            "Away": {"expected_points": 52, "title_probability": 0.01},
        }
    }
    outcomes = {
        "H": {"teams": {"Home": {"expected_points": 80, "title_probability": 0.5}, "Away": {"expected_points": 50}}},
        "D": {"teams": {"Home": {"expected_points": 78, "title_probability": 0.42}, "Away": {"expected_points": 53}}},
        "A": {"teams": {"Home": {"expected_points": 75, "title_probability": 0.3}, "Away": {"expected_points": 56}}},
    }

    breakdown = build_match_breakdown(
        {"home_team": "Home", "away_team": "Away"},
        primary,
        comparison_models={"alternative": comparison},
        results=results,
        strengths={
            "Home": {"rating": 1700, "attack_strength": 1.2, "defense_strength": 0.8},
            "Away": {"rating": 1600, "attack_strength": 1.0, "defense_strength": 1.1},
        },
        calibration={"test_scoreline": {"ece": 0.03, "sample_size": 500}},
        season_forecast=baseline,
        outcome_forecasts=outcomes,
    )

    assert breakdown.probabilities == pytest.approx(
        {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}
    )
    assert breakdown.expected_goals == pytest.approx({"home": 1.4, "away": 0.6, "total": 2.0})
    assert breakdown.top_scorelines[0]["score"] == "2-0"
    assert breakdown.goal_markets["over_under_2_5"]["over"] == pytest.approx(0.1)
    assert breakdown.goal_markets["both_teams_to_score"]["yes"] == pytest.approx(0.4)
    assert breakdown.goal_markets["clean_sheet"]["home"] == pytest.approx(0.4)
    assert breakdown.recent_form["home"]["sequence"] == ["W"]
    assert breakdown.recent_form["away"]["sequence"] == ["D"]
    assert set(breakdown.model_comparison) == {"test_scoreline", "alternative"}
    assert breakdown.confidence["calibration"]["status"] == "well_calibrated"
    assert breakdown.season_impact["Home"]["swing"]["expected_points"] == 5
    assert breakdown.season_impact["Home"]["change_from_baseline"]["home_win"]["expected_points"] == 3


def test_artifacts_are_versioned_serializable_and_vercel_ready(tmp_path):
    teams = ["A", "B"]
    forecast = simulate_season(
        [{"home_team": "A", "away_team": "B"}],
        GridModel(_grid((1, 0, 1.0))),
        teams=teams,
        n_simulations=2,
        seed=1,
        qualification_slots={"champions_league": (1,)},
        relegation_slots=(2,),
    )
    breakdown = build_match_breakdown(
        {"home_team": "A", "away_team": "B"},
        GridModel(_grid((1, 0, 1.0))),
    )
    generated_at = "2026-08-27T12:00:00Z"
    artifact = season_forecast_artifact(forecast, generated_at=generated_at)
    breakdown_json = match_breakdown_artifact(breakdown, generated_at=generated_at)

    assert artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert artifact["product"] == "domestic_league"
    assert artifact["data"]["teams"]["A"]["title_probability"] == 1
    assert breakdown_json["artifact_type"] == "match_breakdown"

    path = write_json_artifact(tmp_path / "forecast.json", artifact, pretty=True)
    assert read_json_artifact(path) == artifact

    response = vercel_response(artifact)
    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"].startswith("application/json")
    assert json.loads(response["body"]) == artifact

    world_cup = artifact_envelope(
        product="world_cup",
        artifact_type="tournament_forecast",
        data={"winner": {"Spain": np.float64(0.2)}},
        generated_at=generated_at,
    )
    assert world_cup["product"] == "world_cup"
    assert world_cup["data"]["winner"]["Spain"] == 0.2
