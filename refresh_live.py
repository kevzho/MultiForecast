"""Refresh Big Five live scores, odds and Vercel artifacts every 15 minutes."""
from __future__ import annotations

import os
from pathlib import Path

from domestic.config import list_leagues
from domestic.odds import append_snapshots, fetch_odds
from domestic.sources import refresh_current_schedule
from export_forecasts import export_forecasts


def main() -> int:
    odds_key = os.getenv("ODDS_API_KEY")
    odds_region = os.getenv("ODDS_REGION", "uk")
    failures = []
    for league in list_leagues():
        try:
            schedule = refresh_current_schedule(league)
            print(f"{league.name}: refreshed {len(schedule)} fixtures")
        except Exception as exc:
            failures.append(league.slug)
            print(f"WARN: {league.name} refresh failed: {exc}")
            continue
        if odds_key:
            try:
                append_snapshots(fetch_odds(league, schedule, api_key=odds_key, region=odds_region))
            except Exception as exc:
                print(f"WARN: {league.name} odds unavailable: {exc}")
    if len(failures) == len(list_leagues()):
        raise RuntimeError("All domestic refreshes failed; no artifact was published")
    export_forecasts(
        output_dir=Path(__file__).resolve().parent / "web" / "public" / "data",
        run_validation=False,
        n_simulations=int(os.getenv("LIVE_SIMULATIONS", "500")),
        impact_matches=0,
        include_worldcup=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
