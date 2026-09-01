"""Full-season fixture sources for domestic competitions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from domestic.config import DEFAULT_DATA_ROOT, LeagueConfig, data_paths, get_league, season_code
from domestic.data import (
    CANONICAL_COLUMNS,
    DataFetchError,
    fetch_matches,
    normalize_team,
    save_matches,
    validate_matches,
)


ESPN_LEAGUES = {
    "premier_league": "eng.1",
    "serie_a": "ita.1",
    "ligue_1": "fra.1",
    "la_liga": "esp.1",
    "bundesliga": "ger.1",
}
ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/"
    "{league}/scoreboard"
)


def _season_window(code: str) -> tuple[str, str]:
    start_year = 2000 + int(code[:2])
    return f"{start_year}0701", f"{start_year + 1}0630"


def _competitor(competition: dict[str, Any], side: str) -> dict[str, Any] | None:
    for item in competition.get("competitors", []):
        if item.get("homeAway") == side:
            return item
    return None


def _repair_pair_orientation(frame: pd.DataFrame) -> pd.DataFrame:
    repaired = frame.copy()
    pair_key = repaired.apply(
        lambda row: tuple(sorted((row["home_team"], row["away_team"]))),
        axis=1,
    )
    for _, indexes in repaired.groupby(pair_key).groups.items():
        group = repaired.loc[list(indexes)]
        if len(group) != 2:
            continue
        first, second = group.iloc[0], group.iloc[1]
        if first["home_team"] != second["home_team"]:
            continue
        candidates = group[group["status"] != "played"]
        target = candidates.index[-1] if not candidates.empty else group.index[-1]
        home = repaired.at[target, "home_team"]
        repaired.at[target, "home_team"] = repaired.at[target, "away_team"]
        repaired.at[target, "away_team"] = home
    return repaired


def fetch_espn_schedule(
    league: str | LeagueConfig,
    season: str | int | None = None,
    *,
    session: requests.Session | None = None,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """Fetch every scheduled match and completed score for one season."""

    config = get_league(league)
    code = season_code(season or config.season)
    start, end = _season_window(code)
    client = session or requests
    url = ESPN_SCOREBOARD_URL.format(league=ESPN_LEAGUES[config.slug])
    response = client.get(
        url,
        params={"dates": f"{start}-{end}", "limit": 1000},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    updated = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        home = _competitor(competition, "home")
        away = _competitor(competition, "away")
        if home is None or away is None:
            continue
        home_name = normalize_team(home.get("team", {}).get("displayName"), config)
        away_name = normalize_team(away.get("team", {}).get("displayName"), config)
        status_type = competition.get("status", {}).get("type", {})
        state = status_type.get("state", "pre")
        completed = bool(status_type.get("completed")) or state == "post"
        home_score = pd.to_numeric(home.get("score"), errors="coerce") if completed else pd.NA
        away_score = pd.to_numeric(away.get("score"), errors="coerce") if completed else pd.NA
        rows.append(
            {
                "league": config.slug,
                "season": code,
                "date": pd.to_datetime(event.get("date"), errors="coerce", utc=True),
                "home_team": home_name,
                "away_team": away_name,
                "home_goals": home_score,
                "away_goals": away_score,
                "status": "played" if completed else ("live" if state == "in" else "scheduled"),
                "source_updated_at": updated,
            }
        )
    frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    if frame.empty:
        raise DataFetchError(f"ESPN returned no fixtures for {config.name} {code}")
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce").astype("Int64")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce").astype("Int64")
    frame = _repair_pair_orientation(frame)
    frame = frame.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)
    report = validate_matches(frame, config, strict=True)
    report.raise_if_invalid()
    frame.attrs.update(data_source="espn", source_url=response.url, used_cache=False)
    return frame


def merge_results(
    schedule: pd.DataFrame,
    results: pd.DataFrame,
) -> pd.DataFrame:
    """Overlay completed scores without dropping the future schedule."""

    keys = ["league", "season", "home_team", "away_team"]
    result_columns = keys + ["home_goals", "away_goals", "status", "source_updated_at"]
    played = results.dropna(subset=["home_goals", "away_goals"])[result_columns]
    if played.empty:
        return schedule.copy()
    merged = schedule.merge(played, on=keys, how="left", suffixes=("", "_result"))
    has_result = merged["home_goals_result"].notna() & merged["away_goals_result"].notna()
    for column in ("home_goals", "away_goals", "status", "source_updated_at"):
        result_column = f"{column}_result"
        merged.loc[has_result, column] = merged.loc[has_result, result_column]
        merged = merged.drop(columns=result_column)
    return merged.loc[:, CANONICAL_COLUMNS].copy()


def refresh_current_schedule(
    league: str | LeagueConfig,
    season: str | int | None = None,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Refresh a full schedule, with the local processed file as fallback."""

    config = get_league(league)
    code = season_code(season or config.season)
    paths = data_paths(config, code, data_root)
    try:
        schedule = fetch_espn_schedule(config, code, session=session)
    except (requests.RequestException, ValueError, DataFetchError) as exc:
        if not paths.processed.exists():
            raise DataFetchError(
                f"Could not refresh the {config.name} schedule and no local copy exists: {exc}"
            ) from exc
        cached = pd.read_csv(paths.processed)
        cached["date"] = pd.to_datetime(cached["date"], errors="coerce")
        cached["home_goals"] = pd.to_numeric(cached["home_goals"], errors="coerce").astype("Int64")
        cached["away_goals"] = pd.to_numeric(cached["away_goals"], errors="coerce").astype("Int64")
        cached["source_updated_at"] = pd.to_datetime(
            cached["source_updated_at"], errors="coerce", utc=True
        )
        cached.attrs.update(data_source="last_known_good", used_cache=True, refresh_error=str(exc))
        return cached

    try:
        football_data = fetch_matches(
            config,
            code,
            data_root=data_root,
            session=session,
        )
    except DataFetchError:
        football_data = pd.DataFrame(columns=CANONICAL_COLUMNS)
    combined = merge_results(schedule, football_data)
    report = validate_matches(combined, config, strict=True)
    report.raise_if_invalid()
    save_matches(combined, paths.processed)
    combined.attrs.update(
        data_source="espn+football-data" if not football_data.empty else "espn",
        used_cache=False,
    )
    return combined


__all__ = [
    "ESPN_LEAGUES",
    "fetch_espn_schedule",
    "merge_results",
    "refresh_current_schedule",
]
