import importlib
import math
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


MOVED_MODULES = [
    "premier_league.cache_manager",
    "premier_league.data_processor",
    "premier_league.run",
    "premier_league.refresh",
    "premier_league.engine.cache_utils",
    "premier_league.engine.config",
    "premier_league.engine.elo",
    "premier_league.engine.elo_run",
    "premier_league.engine.fetch_data",
    "premier_league.engine.load_data",
    "premier_league.engine.pipeline",
    "premier_league.engine.remaining_fixtures",
    "premier_league.engine.simulation",
    "premier_league.engine.table",
    "premier_league.engine.team_names",
]


def test_moved_premier_league_modules_import():
    for module_name in MOVED_MODULES:
        importlib.import_module(module_name)


def test_tiny_fixed_seed_premier_league_simulation_outputs_in_range():
    from premier_league.engine.simulation import simulate_season

    random.seed(2026)
    teams = ["Arsenal", "Man City", "Liverpool", "Chelsea"]
    ratings = {
        "Arsenal": 1700,
        "Man City": 1680,
        "Liverpool": 1660,
        "Chelsea": 1600,
    }
    current_table = {
        team: {"points": 0, "played": 0, "wins": 0, "draws": 0, "losses": 0}
        for team in teams
    }
    fixtures = pd.DataFrame(
        [
            {"HomeTeam": "Arsenal", "AwayTeam": "Man City"},
            {"HomeTeam": "Liverpool", "AwayTeam": "Chelsea"},
            {"HomeTeam": "Man City", "AwayTeam": "Chelsea"},
            {"HomeTeam": "Arsenal", "AwayTeam": "Liverpool"},
        ]
    )

    results = simulate_season(
        fixtures,
        ratings,
        current_table,
        n_sims=5,
        home_adv=65,
        draw_rate=0.26,
    )

    for team_result in results.values():
        for key in ("title_prob", "top4_prob", "relegation_prob", "expected_points"):
            assert key in team_result
            value = team_result[key]
            assert math.isfinite(value)
            if key != "expected_points":
                assert 0 <= value <= 1

    assert math.isclose(sum(team["title_prob"] for team in results.values()), 1)
