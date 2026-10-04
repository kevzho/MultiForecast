"""Licensed live match and official-table snapshots for the Big Five."""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import get_close_matches
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd
import requests

from domestic.config import DEFAULT_DATA_ROOT, LeagueConfig, get_league
from domestic.data import normalize_team, validate_matches

COMPETITIONS = {"premier_league": "PL", "serie_a": "SA", "ligue_1": "FL1", "la_liga": "PD", "bundesliga": "BL1"}
API = "https://api.football-data.org/v4/competitions/{code}/{resource}"


def fixture_id(league: str, season: str, home: str, away: str) -> str:
    def slug(value: str) -> str:
        text = unicodedata.normalize("NFKD", value.casefold())
        text = "".join(c for c in text if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return f"{league}-{season}-{slug(home)}-{slug(away)}"


def _resolve(name: str, teams: set[str], league: LeagueConfig) -> str | None:
    normalized = normalize_team(name, league)
    if normalized in teams:
        return normalized
    def key(value: str) -> str:
        value = unicodedata.normalize("NFKD", value.casefold())
        value = "".join(c for c in value if not unicodedata.combining(c))
        return re.sub(r"\b(fc|afc|ac|sc|cf|calcio|club|football|1909|1907)\b|[^a-z0-9]", "", value)
    matches = [team for team in teams if key(team) == key(normalized)]
    if len(matches) == 1:
        return matches[0]
    lookup = {key(team): team for team in teams}
    close = get_close_matches(key(normalized), lookup, n=2, cutoff=0.88)
    return lookup[close[0]] if len(close) == 1 else None


def fetch_live_snapshot(league: str | LeagueConfig, *, token: str, session: requests.Session | None = None, data_root: str | Path = DEFAULT_DATA_ROOT) -> dict:
    config = get_league(league)
    client = session or requests
    code = COMPETITIONS[config.slug]
    now = datetime.now(timezone.utc).isoformat()
    payloads = {}
    for resource in ("matches", "standings"):
        response = client.get(API.format(code=code, resource=resource), headers={"X-Auth-Token": token}, params={"season": 2000 + int(config.season[:2])}, timeout=25)
        response.raise_for_status()
        payloads[resource] = response.json()
    matches = payloads["matches"].get("matches", [])
    standings = next((item.get("table", []) for item in payloads["standings"].get("standings", []) if item.get("type") == "TOTAL"), [])
    if len(matches) < config.expected_matches or len(standings) != config.team_count:
        raise ValueError(f"Incomplete licensed snapshot for {config.slug}")
    snapshot = {"league": config.slug, "season": config.season, "capturedAt": now, "source": "football-data.org", "fixtures": [], "officialStandings": []}
    for match in matches:
        score = match.get("score", {}).get("fullTime") or {}
        snapshot["fixtures"].append({
            "sourceId": str(match["id"]), "kickoff": match.get("utcDate"), "status": match.get("status"),
            "homeTeam": match.get("homeTeam", {}).get("name"), "awayTeam": match.get("awayTeam", {}).get("name"),
            "homeScore": score.get("home"), "awayScore": score.get("away"), "sourceUpdatedAt": match.get("lastUpdated"),
        })
    for row in standings:
        snapshot["officialStandings"].append({
            "sourceTeamId": str(row.get("team", {}).get("id")), "team": row.get("team", {}).get("name"),
            "position": row.get("position"), "played": row.get("playedGames"), "points": row.get("points"),
            "goalDifference": row.get("goalDifference"), "sourceUpdatedAt": now,
        })
    return snapshot


def save_live_snapshot(snapshot: dict, *, data_root: str | Path = DEFAULT_DATA_ROOT) -> None:
    path = Path(data_root) / "live" / f"{snapshot['league']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_live_snapshot(league: str | LeagueConfig, *, data_root: str | Path = DEFAULT_DATA_ROOT) -> dict | None:
    path = Path(data_root) / "live" / f"{get_league(league).slug}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def apply_live_scores(schedule: pd.DataFrame, snapshot: dict, league: str | LeagueConfig) -> pd.DataFrame:
    """Overlay provider results only on uniquely identified scheduled fixtures."""
    config = get_league(league)
    result = schedule.copy()
    teams = set(result.home_team) | set(result.away_team)
    by_pair = {(row.home_team, row.away_team): index for index, row in result.iterrows()}
    matched = 0
    for fixture in snapshot["fixtures"]:
        home = _resolve(fixture["homeTeam"] or "", teams, config)
        away = _resolve(fixture["awayTeam"] or "", teams, config)
        index = by_pair.get((home, away))
        if index is None:
            continue
        matched += 1
        status = fixture["status"]
        if status in ("FINISHED", "AWARDED") and fixture["homeScore"] is not None and fixture["awayScore"] is not None:
            result.at[index, "home_goals"] = int(fixture["homeScore"])
            result.at[index, "away_goals"] = int(fixture["awayScore"])
            result.at[index, "status"] = "played"
        elif status in ("IN_PLAY", "PAUSED", "HALFTIME", "EXTRA_TIME", "PENALTY_SHOOTOUT"):
            result.at[index, "status"] = "live"
        if fixture["kickoff"]:
            result.at[index, "date"] = pd.Timestamp(fixture["kickoff"])
        result.at[index, "source_updated_at"] = pd.Timestamp(fixture["sourceUpdatedAt"] or snapshot["capturedAt"])
    if matched < max(1, int(len(result) * 0.8)):
        raise ValueError(f"Only matched {matched}/{len(result)} licensed fixtures; keeping last valid schedule")
    validate_matches(result, config).raise_if_invalid()
    return result
