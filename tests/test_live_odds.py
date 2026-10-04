from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from domestic.live_data import apply_live_scores, fixture_id
from domestic.odds import COLUMNS, append_snapshots, blend_grid, consensus_1x2, load_odds
from evaluate_bets import evaluate


def test_live_overlay_uses_provider_ids_and_keeps_live_scores_out_of_training():
    schedule = pd.DataFrame([
        {"league": "premier_league", "season": "2627", "date": "2026-09-28T18:00:00Z", "home_team": "Manchester City", "away_team": "Liverpool", "home_goals": pd.NA, "away_goals": pd.NA, "status": "scheduled", "source_updated_at": "2026-09-28T12:00:00Z"},
    ])
    snapshot = {"capturedAt": "2026-09-28T18:30:00Z", "fixtures": [{"sourceId": "123", "homeTeam": "Manchester City FC", "awayTeam": "Liverpool FC", "homeScore": 1, "awayScore": 0, "status": "IN_PLAY", "kickoff": "2026-09-28T18:00:00Z", "sourceUpdatedAt": "2026-09-28T18:29:00Z"}]}
    result = apply_live_scores(schedule, snapshot, "premier_league")
    assert result.iloc[0].status == "live"
    assert pd.isna(result.iloc[0].home_goals)
    snapshot["fixtures"][0]["status"] = "FINISHED"
    result = apply_live_scores(schedule, snapshot, "premier_league")
    assert result.iloc[0].home_goals == 1
    assert result.iloc[0].status == "played"


def test_odds_snapshots_are_pre_kickoff_and_margin_is_removed(tmp_path):
    kickoff = datetime.now(timezone.utc) + timedelta(hours=2)
    fixture = fixture_id("premier_league", "2627", "Manchester City", "Liverpool")
    rows = [(fixture, (kickoff - timedelta(hours=1)).isoformat(), "book", "1x2", side, price, "snapshot", "the-odds-api", "abc", kickoff.isoformat(), "Manchester City", "Liverpool") for side, price in (("home", 2.0), ("draw", 4.0), ("away", 4.0))]
    path = tmp_path / "odds.csv"
    first = append_snapshots(pd.DataFrame(rows, columns=COLUMNS), path=path)
    assert len(first) == 3
    assert len(append_snapshots(pd.DataFrame(rows, columns=COLUMNS), path=path)) == 3
    market, prices = consensus_1x2(load_odds(path), fixture)
    assert np.allclose(market, [0.5, 0.25, 0.25])
    assert prices["home"] == 2.0
    grid = np.ones((11, 11)) / 121
    assert np.allclose(blend_grid(grid, market, 1).wdl, market)


def test_personal_bets_are_evaluated_against_real_results_only():
    fixture = fixture_id("premier_league", "2627", "Manchester City", "Liverpool")
    matches = pd.DataFrame([{"league": "premier_league", "season": "2627", "home_team": "Manchester City", "away_team": "Liverpool", "home_goals": 2, "away_goals": 1}])
    bets = pd.DataFrame([{"fixture_id": fixture, "market": "1x2", "selection": "home", "decimal_odds": 2.5, "stake": 10, "model_probability": 0.6}])
    result = evaluate(bets, matches)
    assert result["profit"] == 15
    assert result["roi"] == 1.5
    assert abs(result["brier"] - 0.16) < 1e-9
