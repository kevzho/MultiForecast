import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from premier_league.engine.config import ACTIVE_TEAMS_2627, PROMOTED_ELO_SEEDS_2627, SEASON
from premier_league.engine.load_data import load_current_table, load_power_rankings, load_season_df, split_played_future
from premier_league.engine.remaining_fixtures import generate_placeholder_fixtures, get_remaining_fixtures
from premier_league.engine.team_names import CANONICAL_TEAMS, normalize_team


RELEGATED = {"West Ham", "Burnley", "Wolves"}
PROMOTED = {"Coventry City", "Ipswich Town", "Hull City"}


def test_2026_27_roster_and_aliases():
    assert SEASON == "2627"
    assert set(ACTIVE_TEAMS_2627) == CANONICAL_TEAMS
    assert not RELEGATED.intersection(CANONICAL_TEAMS)
    assert PROMOTED <= CANONICAL_TEAMS
    assert normalize_team("Coventry") == "Coventry City"
    assert normalize_team("Ipswich") == "Ipswich Town"
    assert normalize_team("Hull") == "Hull City"


def test_2026_27_data_has_20_teams_and_all_future_matches():
    ratings = load_power_rankings()
    table = load_current_table()
    season_df = load_season_df()
    played, future = split_played_future(season_df)

    assert set(ratings) == CANONICAL_TEAMS
    assert set(table) == CANONICAL_TEAMS
    assert len(season_df) == 380
    assert played.empty
    assert len(future) == 380
    assert all(team in ratings for team in PROMOTED)


def test_placeholder_fixture_generation_is_double_round_robin():
    fixtures = generate_placeholder_fixtures()
    pairs = fixtures.groupby(["HomeTeam", "AwayTeam"]).size()

    assert len(fixtures) == 380
    assert pairs.min() == 1
    assert pairs.max() == 1
    assert set(fixtures["HomeTeam"]).union(fixtures["AwayTeam"]) == CANONICAL_TEAMS


def test_promoted_elo_seed_order():
    assert PROMOTED_ELO_SEEDS_2627["Coventry City"] > PROMOTED_ELO_SEEDS_2627["Ipswich Town"]
    assert PROMOTED_ELO_SEEDS_2627["Ipswich Town"] > PROMOTED_ELO_SEEDS_2627["Hull City"]
