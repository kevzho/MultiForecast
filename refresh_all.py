"""Refresh source data and publish artifacts for both applications."""

import os

from domestic.refresh import refresh_leagues
from export_forecasts import export_forecasts
from worldcup.refresh import main as refresh_worldcup


def main() -> int:
    export_failed = False
    domestic_status = refresh_leagues()
    if domestic_status and all(
        value.startswith("failed:") for value in domestic_status.values()
    ):
        print("WARN: All domestic source refreshes failed; using cached schedules")
    try:
        refresh_worldcup()
    except Exception as exc:
        print(f"WARN: World Cup refresh failed: {exc}")

    try:
        export_forecasts(
            n_simulations=int(os.getenv("FORECAST_SIMULATIONS", "5000")),
            worldcup_simulations=int(os.getenv("WORLDCUP_SIMULATIONS", "5000")),
            impact_matches=int(os.getenv("FORECAST_IMPACT_MATCHES", "3")),
            impact_simulations=int(os.getenv("FORECAST_IMPACT_SIMULATIONS", "300")),
        )
    except Exception as exc:
        export_failed = True
        print(f"WARN: Forecast export failed: {exc}")
    return 1 if export_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
