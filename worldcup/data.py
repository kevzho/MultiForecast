"""Load and validate the self-contained 2026 World Cup data layer."""

from pathlib import Path

import pandas as pd

from worldcup.team_names import CANONICAL_WC_TEAMS, normalize_intl_team

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "wc"


def load_groups() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "wc2026_groups.csv")


def load_fixtures() -> pd.DataFrame:
    fixtures = pd.read_csv(DATA_DIR / "wc2026_fixtures.csv")
    fixtures["Date"] = pd.to_datetime(fixtures["Date"])
    fixtures["Neutral"] = fixtures["Neutral"].astype(bool)
    return fixtures


def load_results() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "wc2026_results.csv")


def load_elo() -> dict[str, int]:
    elo = pd.read_csv(DATA_DIR / "intl_elo_ratings.csv")
    return dict(zip(elo["Team"], elo["Elo"]))


def merge_played(fixtures: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    merged = fixtures.merge(results, on="MatchID", how="left")
    merged["Played"] = merged["FTHG"].notna() & merged["FTAG"].notna()
    return merged


def validate() -> dict[str, int]:
    groups = load_groups()
    fixtures = load_fixtures()
    elo = load_elo()

    teams = groups["Team"].map(normalize_intl_team)
    assert len(teams) == 48, f"Expected 48 teams, found {len(teams)}"
    assert teams.nunique() == 48, "Duplicate teams found in groups"
    assert set(teams) == CANONICAL_WC_TEAMS, "Group teams do not match canonical set"

    group_sizes = groups.groupby("Group")["Team"].nunique()
    assert len(group_sizes) == 12, f"Expected 12 groups, found {len(group_sizes)}"
    assert (group_sizes == 4).all(), "Every group must contain exactly 4 teams"

    normalized_elo_teams = {normalize_intl_team(team) for team in elo}
    missing_elo = CANONICAL_WC_TEAMS - normalized_elo_teams
    assert not missing_elo, f"Missing Elo ratings for: {sorted(missing_elo)}"

    group_fixtures = fixtures[fixtures["Stage"] == "Group"]
    assert len(group_fixtures) == 72, f"Expected 72 group fixtures, found {len(group_fixtures)}"

    fixture_teams = set(group_fixtures["HomeTeam"]).union(group_fixtures["AwayTeam"])
    normalized_fixture_teams = {normalize_intl_team(team) for team in fixture_teams}
    assert normalized_fixture_teams <= CANONICAL_WC_TEAMS, "Unknown team in group fixtures"

    return {
        "teams": len(teams),
        "groups": len(group_sizes),
        "group_fixtures": len(group_fixtures),
        "fixtures": len(fixtures),
        "elo_teams": len(normalized_elo_teams),
    }


if __name__ == "__main__":
    summary = validate()
    print(
        "World Cup data OK: "
        f"{summary['teams']} teams, "
        f"{summary['groups']} groups, "
        f"{summary['group_fixtures']} group fixtures, "
        f"{summary['fixtures']} total fixtures, "
        f"{summary['elo_teams']} Elo ratings."
    )

