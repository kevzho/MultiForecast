"""Fetch additional real historical seasons from football-data.co.uk."""
from domestic.config import data_paths, list_leagues, previous_season_codes
from domestic.data import fetch_matches


def main() -> int:
    failures = []
    for league in list_leagues():
        for season in previous_season_codes(league.season, 10)[:-1]:
            if data_paths(league, season).processed.exists():
                continue
            try:
                matches = fetch_matches(league, season)
                print(f"{league.name} {season}: {len(matches)} real matches")
            except Exception as exc:
                failures.append((league.slug, season))
                print(f"WARN: {league.name} {season} backfill failed: {exc}")
    print(f"Historical backfill: {len(failures)} unavailable seasons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
