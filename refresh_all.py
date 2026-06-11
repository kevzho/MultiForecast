"""Top-level daily refresh orchestrator for MultiForecast."""

from premier_league.refresh import main as refresh_premier_league
from worldcup.refresh import main as refresh_worldcup


def main() -> int:
    failures = 0
    for label, refresh in (
        ("Premier League refresh", refresh_premier_league),
        ("World Cup refresh", refresh_worldcup),
    ):
        try:
            refresh()
        except Exception as e:
            failures += 1
            print(f"WARN: {label} failed: {e}")
    return 1 if failures == 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
