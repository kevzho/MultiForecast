"""Build the forecast artifacts consumed by the Vercel application."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

from domestic.config import LeagueConfig, get_league, list_leagues
from domestic.pipeline import ForecastRun, build_breakdown_with_impact, build_forecast
from domestic.sources import refresh_current_schedule
from domestic.live_data import _resolve, fixture_id, load_live_snapshot
from domestic.odds import consensus_1x2, consensus_binary, load_odds
from domestic.standings import build_table, table_as_records
from worldcup.artifacts import (
    ARTIFACT_VERSION,
    SCHEMA_VERSION,
    build_worldcup_artifact,
)


DEFAULT_OUTPUT = Path(__file__).resolve().parent / "web" / "public" / "data"


def _id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unknown"


def _team_ref(team: str) -> dict[str, str]:
    return {"id": _id(team), "name": team, "shortName": team}


def _model_probabilities(breakdown: Any) -> list[dict[str, Any]]:
    rows = []
    for model, comparison in breakdown.model_comparison.items():
        probabilities = comparison["probabilities"]
        rows.append(
            {
                "model": model,
                "homeWin": float(probabilities["home_win"]),
                "draw": float(probabilities["draw"]),
                "awayWin": float(probabilities["away_win"]),
            }
        )
    return rows


def _objective_metric(team_forecast: Any) -> str:
    if team_forecast.title_probability >= 0.05:
        return "title_probability"
    if team_forecast.europe_probability >= 0.05:
        return "europe_probability"
    return "relegation_probability"


def _impact_rows(run: ForecastRun, breakdown: Any) -> list[dict[str, Any]]:
    if not breakdown.season_impact:
        return []
    home = breakdown.home_team
    away = breakdown.away_team
    metrics = {
        home: _objective_metric(run.forecast.teams[home]),
        away: _objective_metric(run.forecast.teams[away]),
    }
    aliases = {
        "home_win": ("home", f"{home} win"),
        "draw": ("draw", "Draw"),
        "away_win": ("away", f"{away} win"),
    }
    rows = []
    for source, (outcome, label) in aliases.items():
        values = {}
        for team in (home, away):
            changes = breakdown.season_impact.get(team, {}).get(
                "change_from_baseline"
            ) or {}
            values[team] = changes.get(source, {}).get(metrics[team])
        rows.append(
            {
                "outcome": outcome,
                "label": label,
                "homeDelta": values[home],
                "awayDelta": values[away],
            }
        )
    return rows


def _match_forecast(run: ForecastRun, breakdown: Any, market: Any = None, totals_market: Any = None, btts_market: Any = None) -> dict[str, Any]:
    probabilities = breakdown.probabilities
    goals = breakdown.expected_goals
    markets = breakdown.goal_markets
    result = {
        "homeWin": float(probabilities["home_win"]),
        "draw": float(probabilities["draw"]),
        "awayWin": float(probabilities["away_win"]),
        "expectedHomeGoals": float(goals["home"]),
        "expectedAwayGoals": float(goals["away"]),
        "over25": float(markets["over_under_2_5"]["over"]),
        "bothTeamsScore": float(markets["both_teams_to_score"]["yes"]),
        "homeCleanSheet": float(markets["clean_sheet"]["home"]),
        "awayCleanSheet": float(markets["clean_sheet"]["away"]),
        "topScorelines": [
            {
                "home": int(row["home_goals"]),
                "away": int(row["away_goals"]),
                "probability": float(row["probability"]),
            }
            for row in breakdown.top_scorelines
        ],
        "modelProbabilities": _model_probabilities(breakdown),
        "seasonImpact": _impact_rows(run, breakdown),
        "uncertainty": {
            "normalizedEntropy": float(-sum(p * np.log(p) for p in (probabilities["home_win"], probabilities["draw"], probabilities["away_win"]) if p > 0) / np.log(3)),
            "calibration": breakdown.confidence.get("calibration"),
        },
    }
    if market is not None:
        implied, prices = market
        probs = [result["homeWin"], result["draw"], result["awayWin"]]
        result["market"] = {
            "implied": {key: float(value) for key, value in zip(("home", "draw", "away"), implied)},
            "bestDecimalOdds": prices,
            "expectedValue": {key: float(probability * prices[key] - 1) for key, probability in zip(("home", "draw", "away"), probs) if key in prices},
            "entropy": float(-sum(p * np.log(p) for p in probs if p > 0) / np.log(3)),
        }
    for key, quote, probability in (("totals_2_5", totals_market, result["over25"]), ("btts", btts_market, result["bothTeamsScore"])):
        if quote is not None:
            implied, prices = quote
            positive = "over" if key == "totals_2_5" else "yes"
            negative = "under" if key == "totals_2_5" else "no"
            result.setdefault("otherMarkets", {})[key] = {
                "implied": implied,
                "bestDecimalOdds": prices,
                "expectedValue": {positive: float(probability * prices[positive] - 1), negative: float((1 - probability) * prices[negative] - 1)},
            }
    return result


def _standing_rows(run: ForecastRun) -> list[dict[str, Any]]:
    current = {row["team"]: row for row in run.forecast.current_table}
    ordered = sorted(
        run.forecast.teams.values(),
        key=lambda value: (value.expected_position, -value.expected_points),
    )
    rows = []
    for position, forecast in enumerate(ordered, start=1):
        table = current.get(forecast.team, {})
        rows.append(
            {
                "position": position,
                "team": _team_ref(forecast.team),
                "played": int(table.get("played", 0)),
                "points": int(table.get("points", 0)),
                "goalDifference": int(table.get("goal_difference", 0)),
                "expectedPoints": float(forecast.expected_points),
                "expectedPosition": float(forecast.expected_position),
                "titleProbability": float(forecast.title_probability),
                "championsLeagueProbability": float(
                    forecast.qualification_probabilities.get("champions_league", 0.0)
                ),
                "relegationProbability": float(forecast.relegation_probability),
                "positionProbabilities": list(forecast.position_probabilities),
            }
        )
    return rows


def _fixture_rows(
    run: ForecastRun,
    *,
    impact_matches: int,
    impact_simulations: int,
) -> list[dict[str, Any]]:
    snapshots = load_odds()
    live = load_live_snapshot(run.config)
    live_by_id = {}
    if live:
        teams = set(run.matches.home_team) | set(run.matches.away_team)
        for item in live["fixtures"]:
            home = _resolve(item.get("homeTeam") or "", teams, run.config)
            away = _resolve(item.get("awayTeam") or "", teams, run.config)
            if home and away:
                live_by_id[fixture_id(run.config.slug, run.config.season, home, away)] = item
    breakdowns = {
        (item.home_team, item.away_team): item for item in run.breakdowns
    }
    scheduled = run.matches[run.matches["status"] != "played"].sort_values("date")
    for row in scheduled.head(max(0, impact_matches)).itertuples(index=False):
        breakdowns[(row.home_team, row.away_team)] = build_breakdown_with_impact(
            run,
            row,
            n_simulations=impact_simulations,
            seed=420,
        )

    fixtures = []
    for row in run.matches.sort_values("date").itertuples(index=False):
        stable_id = fixture_id(run.config.slug, run.config.season, row.home_team, row.away_team)
        live_item = live_by_id.get(stable_id)
        market = consensus_1x2(snapshots, stable_id, before=row.date) if not snapshots.empty else None
        totals_market = consensus_binary(snapshots, stable_id, "totals_2_5", before=row.date) if not snapshots.empty else None
        btts_market = consensus_binary(snapshots, stable_id, "btts", before=row.date) if not snapshots.empty else None
        played = pd.notna(row.home_goals) and pd.notna(row.away_goals)
        breakdown = breakdowns.get((row.home_team, row.away_team))
        status = "final" if played else ("live" if row.status == "live" else "scheduled")
        kickoff = pd.Timestamp(row.date)
        if kickoff.tzinfo is None:
            kickoff = kickoff.tz_localize("UTC")
        else:
            kickoff = kickoff.tz_convert("UTC")
        fixtures.append(
            {
                "id": stable_id,
                "sourceId": live_item.get("sourceId") if live_item else None,
                "sourceUpdatedAt": live_item.get("sourceUpdatedAt") if live_item else None,
                "stage": "League",
                "round": None,
                "kickoff": kickoff.isoformat().replace("+00:00", "Z"),
                "venue": None,
                "status": status,
                "homeTeam": _team_ref(row.home_team),
                "awayTeam": _team_ref(row.away_team),
                "score": (
                    {"home": int(row.home_goals), "away": int(row.away_goals)}
                    if played
                    else ({"home": int(live_item["homeScore"]), "away": int(live_item["awayScore"])} if status == "live" and live_item and live_item.get("homeScore") is not None and live_item.get("awayScore") is not None else None)
                ),
                "forecast": (
                    _match_forecast(run, breakdown, market, totals_market, btts_market)
                    if breakdown is not None and not played
                    else None
                ),
            }
        )
    return fixtures


def build_league_artifact(
    run: ForecastRun,
    *,
    impact_matches: int = 3,
    impact_simulations: int = 300,
    include_worldcup: bool = True,
) -> dict[str, Any]:
    live = load_live_snapshot(run.config)
    live_stale = bool(live and (datetime.now(timezone.utc) - datetime.fromisoformat(live["capturedAt"])).total_seconds() > 2700)
    source_times = pd.to_datetime(run.matches["source_updated_at"], errors="coerce", utc=True)
    source_stale = bool(source_times.isna().all() or (datetime.now(timezone.utc) - source_times.max().to_pydatetime()).total_seconds() > 2700)
    official = []
    if live:
        teams = set(run.matches.home_team) | set(run.matches.away_team)
        for row in live["officialStandings"]:
            team = _resolve(row.get("team") or "", teams, run.config)
            if team:
                official.append({**row, "team": _team_ref(team)})
    provisional = []
    if live:
        teams = set(run.matches.home_team) | set(run.matches.away_team)
        played_rows = run.matches.dropna(subset=["home_goals", "away_goals"]).to_dict("records")
        live_rows = []
        for item in live["fixtures"]:
            if item.get("status") not in ("IN_PLAY", "PAUSED", "HALFTIME", "EXTRA_TIME", "PENALTY_SHOOTOUT") or item.get("homeScore") is None or item.get("awayScore") is None:
                continue
            home = _resolve(item.get("homeTeam") or "", teams, run.config)
            away = _resolve(item.get("awayTeam") or "", teams, run.config)
            if home and away:
                live_rows.append({"home_team": home, "away_team": away, "home_goals": item["homeScore"], "away_goals": item["awayScore"]})
        if live_rows:
            combined = played_rows + live_rows
            provisional = [{"team": _team_ref(row["team"]), "position": row["position"], "played": row["played"], "points": row["points"], "goalDifference": row["goal_difference"]} for row in table_as_records(build_table(combined, teams, points_for_win=run.config.points_for_win), ranked=True, tiebreakers=run.config.standings_tiebreakers, results=combined, points_for_win=run.config.points_for_win)]
    played = run.matches.dropna(subset=["home_goals", "away_goals"])
    trained_through = None
    if not played.empty:
        trained_through = pd.Timestamp(played["date"].max()).date().isoformat()
    validation = run.validation[run.validation["model"] == run.selected_model]
    evaluation = None
    if not validation.empty:
        row = validation.iloc[0]
        evaluation = (
            f"Rolling backtest over {int(row['n_predictions'])} matches: "
            f"RPS {row['rps']:.3f}, log loss {row['logloss']:.3f}."
        )
    return {
        "kind": "domestic-league-forecast",
        "schemaVersion": SCHEMA_VERSION,
        "artifactVersion": ARTIFACT_VERSION,
        "status": "stale" if source_stale or live_stale else "ready",
        "isDemo": False,
        "disclaimer": "Forecast probabilities are model estimates, not guarantees.",
        "competition": {
            "id": run.config.slug,
            "name": run.config.name,
            "shortName": run.config.name,
            "country": run.config.country,
            "code": run.config.code,
        },
        "season": "2026/27",
        "generatedAt": run.generated_at,
        "model": {
            "name": run.selected_model,
            "version": ARTIFACT_VERSION,
            "simulations": run.forecast.simulations,
            "trainedThrough": trained_through,
        },
        "coverage": {
            "teamsIncluded": run.forecast.team_count,
            "teamsExpected": run.config.team_count,
            "fixturesIncluded": len(run.matches),
            "fixturesExpected": run.config.expected_matches,
        },
        "standings": _standing_rows(run),
        "officialStandings": official,
        "provisionalStandings": provisional,
        "liveSource": {"name": live["source"], "capturedAt": live["capturedAt"]} if live else None,
        "marketCalibration": run.market_calibration,
        "fixtures": _fixture_rows(
            run,
            impact_matches=impact_matches,
            impact_simulations=impact_simulations,
        ),
        "methodology": {
            "primaryModel": run.selected_model,
            "components": [
                "Elo result baseline",
                "Elo-Poisson scorelines",
                "Attack-defense Poisson and Skellam",
                "Dixon-Coles low-score adjustment",
                "Bradley-Terry Davidson comparison",
                "Scoreline Monte Carlo season simulation",
            ],
            "evaluation": evaluation,
            "assumptions": [
                f"Standings use: {', '.join(run.config.standings_tiebreakers)}.",
                run.config.qualification_note,
            ],
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(payload + "\n", encoding="utf-8")
    temporary.replace(path)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def export_forecasts(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    leagues: Iterable[str | LeagueConfig] | None = None,
    refresh: bool = False,
    run_validation: bool = True,
    n_simulations: int = 2_000,
    worldcup_simulations: int = 2_000,
    impact_matches: int = 3,
    impact_simulations: int = 300,
) -> dict[str, Any]:
    output = Path(output_dir)
    configs = tuple(get_league(item) for item in leagues) if leagues else list_leagues()
    if refresh:
        for config in configs:
            refresh_current_schedule(config)

    generated_at = datetime.now(timezone.utc).isoformat()
    league_entries = []
    for config in configs:
        run = build_forecast(
            config,
            run_validation=run_validation,
            n_simulations=n_simulations,
            seed=42,
        )
        artifact = build_league_artifact(
            run,
            impact_matches=impact_matches,
            impact_simulations=impact_simulations,
        )
        filename = f"{config.slug}.json"
        _write_json(output / filename, artifact)
        league_entries.append(
            {
                "id": config.slug,
                "name": config.name,
                "shortName": config.name,
                "country": config.country,
                "code": config.code,
                "kind": "domestic-league",
                "season": "2026/27",
                "expectedTeams": config.team_count,
                "status": artifact["status"],
                "dataUrl": f"/data/{filename}",
                "generatedAt": run.generated_at,
                "note": config.qualification_note,
            }
        )

    if include_worldcup:
        worldcup = build_worldcup_artifact(n_simulations=worldcup_simulations)
        _write_json(output / "world-cup-2026.json", worldcup)
        worldcup_entry = {
            "id": "world-cup-2026", "name": "FIFA World Cup 2026", "shortName": "World Cup",
            "country": "Canada, Mexico and United States", "code": "WC2026", "kind": "tournament",
            "edition": "2026", "expectedTeams": 48, "status": "ready",
            "dataUrl": "/data/world-cup-2026.json", "generatedAt": worldcup["generatedAt"],
            "note": "48-team group and knockout forecast.",
        }
    else:
        worldcup_entry = json.loads((output / "manifest.json").read_text(encoding="utf-8"))["worldCup"]
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "artifactVersion": ARTIFACT_VERSION,
        "generatedAt": generated_at,
        "leagues": league_entries,
        "worldCup": worldcup_entry,
    }
    _write_json(output / "manifest.json", manifest)
    return manifest


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--league", action="append", default=[])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--simulations", type=int, default=2_000)
    parser.add_argument("--worldcup-simulations", type=int, default=2_000)
    parser.add_argument("--impact-matches", type=int, default=3)
    parser.add_argument("--impact-simulations", type=int, default=300)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    manifest = export_forecasts(
        output_dir=args.output,
        leagues=args.league or None,
        refresh=args.refresh,
        run_validation=not args.skip_validation,
        n_simulations=args.simulations,
        worldcup_simulations=args.worldcup_simulations,
        impact_matches=args.impact_matches,
        impact_simulations=args.impact_simulations,
    )
    print(
        f"Exported {len(manifest['leagues'])} leagues and the World Cup to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
