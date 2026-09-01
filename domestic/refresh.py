"""Refresh current Big Five schedules and results."""

from __future__ import annotations

import argparse

from domestic.config import get_league, list_leagues
from domestic.sources import refresh_current_schedule


def refresh_leagues(leagues: list[str] | None = None) -> dict[str, str]:
    configs = [get_league(value) for value in leagues] if leagues else list(list_leagues())
    status = {}
    for config in configs:
        try:
            matches = refresh_current_schedule(config)
            played = int(matches["home_goals"].notna().sum())
            status[config.slug] = f"ok:{played}/{len(matches)}"
            print(f"{config.name}: {played} played, {len(matches) - played} scheduled")
        except Exception as exc:
            status[config.slug] = f"failed:{exc}"
            print(f"WARN: {config.name} refresh failed: {exc}")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", action="append", default=[])
    args = parser.parse_args()
    status = refresh_leagues(args.league or None)
    return 1 if status and all(value.startswith("failed:") for value in status.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
