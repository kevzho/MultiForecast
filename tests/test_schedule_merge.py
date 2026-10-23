import pandas as pd
import pytest

from domestic.data import CANONICAL_COLUMNS
from domestic.sources import merge_results


@pytest.mark.parametrize("schedule_season,result_season", [(2627, "2627"), ("2627", 2627), (2627.0, "2627")])
def test_merge_results_normalizes_csv_seasons(schedule_season, result_season):
    schedule = pd.DataFrame([
        ["premier_league", schedule_season, "2026-08-21", "Arsenal", "Liverpool", None, None, "scheduled", "2026-08-20"],
        ["premier_league", schedule_season, "2027-01-01", "Liverpool", "Arsenal", None, None, "scheduled", "2026-08-20"],
    ], columns=CANONICAL_COLUMNS)
    results = schedule.iloc[:1].copy()
    results["season"] = result_season
    results["home_goals"] = 2
    results["away_goals"] = 1
    results["status"] = "played"
    results["source_updated_at"] = "2026-08-22"
    original_schedule = schedule.copy(deep=True)
    original_results = results.copy(deep=True)

    merged = merge_results(schedule, results)

    assert len(merged) == 2
    assert merged["season"].tolist() == ["2627", "2627"]
    assert merged.loc[0, ["home_goals", "away_goals", "status", "source_updated_at"]].tolist() == [2, 1, "played", "2026-08-22"]
    assert merged.loc[1, "status"] == "scheduled"
    assert pd.isna(merged.loc[1, "home_goals"])
    pd.testing.assert_frame_equal(schedule, original_schedule)
    pd.testing.assert_frame_equal(results, original_results)


def test_merge_results_without_completed_results_normalizes_season():
    schedule = pd.DataFrame([
        ["premier_league", 2627, "2026-08-21", "Arsenal", "Liverpool", None, None, "scheduled", "2026-08-20"],
    ], columns=CANONICAL_COLUMNS)

    merged = merge_results(schedule, pd.DataFrame(columns=CANONICAL_COLUMNS))

    assert merged["season"].tolist() == ["2627"]
    assert merged["status"].tolist() == ["scheduled"]
