"""Evaluate settled personal bets against real matches; never use bets as labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from domestic.config import list_leagues
from domestic.data import load_history
from domestic.live_data import fixture_id

REQUIRED = {"fixture_id", "market", "selection", "decimal_odds", "stake"}

def evaluate(bets: pd.DataFrame, matches: pd.DataFrame) -> dict:
    missing = REQUIRED - set(bets.columns)
    if missing:
        raise ValueError(f"Missing bet columns: {sorted(missing)}")
    results = {}
    for row in matches.dropna(subset=["home_goals", "away_goals"]).itertuples(index=False):
        identifier = fixture_id(row.league, str(row.season), row.home_team, row.away_team)
        home, away = int(row.home_goals), int(row.away_goals)
        results[identifier] = {
            "1x2": "home" if home > away else "away" if home < away else "draw",
            "totals_2_5": "over" if home + away > 2 else "under",
            "btts": "yes" if home and away else "no",
        }
    settled = []
    for row in bets.itertuples(index=False):
        if row.fixture_id not in results or row.market not in results[row.fixture_id]:
            continue
        stake, price = float(row.stake), float(row.decimal_odds)
        if stake <= 0 or price <= 1:
            raise ValueError("Stake must be positive and decimal odds must exceed 1")
        won = row.selection == results[row.fixture_id][row.market]
        probability = getattr(row, "model_probability", None)
        settled.append({"fixture_id": row.fixture_id, "market": row.market, "won": won, "stake": stake, "profit": stake * (price - 1) if won else -stake, "model_probability": probability})
    total_stake = sum(row["stake"] for row in settled)
    output = {"settledBets": len(settled), "totalStake": total_stake, "profit": sum(row["profit"] for row in settled), "roi": sum(row["profit"] for row in settled) / total_stake if total_stake else None}
    calibrated = [row for row in settled if row["model_probability"] is not None and pd.notna(row["model_probability"])]
    output["brier"] = sum((float(row["model_probability"]) - float(row["won"])) ** 2 for row in calibrated) / len(calibrated) if calibrated else None
    return output

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bets", type=Path, help="Private CSV with fixture_id, market, selection, decimal_odds, stake, optional model_probability")
    args = parser.parse_args()
    history = pd.concat([load_history(league, history_seasons=10) for league in list_leagues()], ignore_index=True)
    print(json.dumps(evaluate(pd.read_csv(args.bets), history), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())