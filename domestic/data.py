"""Canonical match data, validation, and football-data ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import os
import tempfile
import unicodedata
from typing import Iterable, Sequence

import pandas as pd
import requests

from domestic.config import (
    DEFAULT_DATA_ROOT,
    LeagueConfig,
    data_paths,
    get_league,
    previous_season_codes,
    season_code,
)


CANONICAL_COLUMNS = (
    "league",
    "season",
    "date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "status",
    "source_updated_at",
)
FOOTBALL_DATA_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
_RAW_REQUIRED = ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG")


class DataFetchError(RuntimeError):
    pass


class DataValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationReport:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def is_valid(self) -> bool:
        return self.valid

    def raise_if_invalid(self) -> None:
        if self.errors:
            raise DataValidationError("; ".join(self.errors))

    def __bool__(self) -> bool:
        return self.valid


@dataclass(frozen=True, slots=True)
class SeasonRollover:
    returning: tuple[str, ...]
    promoted: tuple[str, ...]
    relegated: tuple[str, ...]


_ALIASES: dict[str, dict[str, str]] = {
    "premier_league": {
        "man city": "Manchester City",
        "manchester city": "Manchester City",
        "man united": "Manchester United",
        "man utd": "Manchester United",
        "manchester utd": "Manchester United",
        "newcastle": "Newcastle United",
        "nott'm forest": "Nottingham Forest",
        "nottingham forest": "Nottingham Forest",
        "spurs": "Tottenham Hotspur",
        "tottenham": "Tottenham Hotspur",
        "west ham": "West Ham United",
        "wolves": "Wolverhampton Wanderers",
        "brighton": "Brighton & Hove Albion",
        "bournemouth": "AFC Bournemouth",
        "leeds": "Leeds United",
        "ipswich": "Ipswich Town",
        "hull": "Hull City",
        "coventry": "Coventry City",
    },
    "serie_a": {
        "ac milan": "Milan",
        "internazionale": "Inter",
        "inter milan": "Inter",
        "juventus turin": "Juventus",
        "as roma": "Roma",
        "ss lazio": "Lazio",
        "hellas verona": "Verona",
    },
    "ligue_1": {
        "paris sg": "Paris Saint-Germain",
        "psg": "Paris Saint-Germain",
        "paris saint germain": "Paris Saint-Germain",
        "marseille": "Olympique Marseille",
        "lyon": "Olympique Lyonnais",
        "st etienne": "Saint-Etienne",
    },
    "la_liga": {
        "ath madrid": "Atletico Madrid",
        "atletico madrid": "Atletico Madrid",
        "atletico": "Atletico Madrid",
        "ath bilbao": "Athletic Club",
        "athletic bilbao": "Athletic Club",
        "barcelona": "Barcelona",
        "real madrid": "Real Madrid",
        "sociedad": "Real Sociedad",
        "betis": "Real Betis",
        "alaves": "Alaves",
        "celta": "Celta Vigo",
    },
    "bundesliga": {
        "bayern munich": "Bayern Munich",
        "bayern munchen": "Bayern Munich",
        "dortmund": "Borussia Dortmund",
        "m'gladbach": "Borussia Monchengladbach",
        "monchengladbach": "Borussia Monchengladbach",
        "leverkusen": "Bayer Leverkusen",
        "rb leipzig": "RB Leipzig",
        "ein frankfurt": "Eintracht Frankfurt",
        "fc koln": "FC Cologne",
    },
}


def _team_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).strip()
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.replace("’", "'").replace("`", "'")
    return " ".join(text.casefold().split())


def normalize_team(team: object, league: str | LeagueConfig) -> str:
    """Normalize a source team name without inventing unknown aliases."""

    if team is None or pd.isna(team):
        return ""
    config = get_league(league)
    return _normalize_team_text(team, config.slug)


def _normalize_team_text(team: object, league_slug: str) -> str:
    if team is None or pd.isna(team):
        return ""
    text = unicodedata.normalize("NFKC", str(team)).strip()
    text = " ".join(text.replace("’", "'").split())
    return _ALIASES.get(league_slug, {}).get(_team_key(text), text)


def football_data_url(
    league: str | LeagueConfig,
    season: str | int | None = None,
) -> str:
    config = get_league(league)
    code = season_code(season or config.season)
    return FOOTBALL_DATA_URL.format(season=code, code=config.code)


def fetch_matches(
    league: str | LeagueConfig,
    season: str | int | None = None,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    session: requests.Session | None = None,
    timeout: float = 15.0,
) -> pd.DataFrame:
    """Fetch and cache a season, falling back to the last valid response."""

    config = get_league(league)
    code = season_code(season or config.season)
    paths = data_paths(config, code, data_root)
    client = session or requests
    url = football_data_url(config, code)
    try:
        response = client.get(url, timeout=timeout)
        response.raise_for_status()
        raw = bytes(response.content)
        matches = _from_football_data(raw, config, code)
        report = validate_matches(matches, config)
        report.raise_if_invalid()
        _write_bytes_atomic(paths.raw, raw)
        _write_bytes_atomic(paths.last_known_good, raw)
        save_matches(matches, paths.processed)
        return _with_source(matches, "remote", url=url, used_cache=False)
    except (requests.RequestException, OSError, ValueError, pd.errors.ParserError) as exc:
        cached = _load_first_available(
            (paths.last_known_good, paths.processed, paths.raw), config, code
        )
        if cached is None:
            raise DataFetchError(
                f"Could not refresh {config.name} {code} and no valid cache exists: {exc}"
            ) from exc
        return _with_source(
            cached,
            "last_known_good",
            url=url,
            used_cache=True,
            refresh_error=str(exc),
        )


def load_matches(
    league: str | LeagueConfig,
    season: str | int | None = None,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    refresh: bool = False,
    include_historical: bool = False,
    history_seasons: int = 5,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Load one canonical season or a current-plus-history training frame."""

    config = get_league(league)
    code = season_code(season or config.season)
    if include_historical:
        if refresh:
            fetch_matches(config, code, data_root=data_root, session=session)
        return load_history(
            config,
            seasons=previous_season_codes(code, history_seasons),
            data_root=data_root,
        )
    if refresh:
        return fetch_matches(config, code, data_root=data_root, session=session)

    paths = data_paths(config, code, data_root)
    legacy = Path(data_root) / f"{config.code}_{code}.csv"
    matches = _load_first_available(
        (paths.processed, paths.last_known_good, paths.raw, legacy), config, code
    )
    if matches is None:
        raise FileNotFoundError(
            f"No data for {config.name} {code}. Expected {paths.processed} or {legacy}."
        )
    return _with_source(matches, "local", used_cache=True)


def load_history(
    league: str | LeagueConfig,
    seasons: Sequence[str | int] | None = None,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    history_seasons: int = 5,
    require_all: bool = False,
) -> pd.DataFrame:
    """Load available seasons in chronological order."""

    config = get_league(league)
    requested = tuple(seasons or previous_season_codes(config.season, history_seasons))
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for value in requested:
        code = season_code(value)
        try:
            frame = load_matches(config, code, data_root=data_root)
        except FileNotFoundError:
            missing.append(code)
            continue
        frames.append(frame)
    if require_all and missing:
        raise FileNotFoundError(f"Missing {config.name} seasons: {', '.join(missing)}")
    if not frames:
        raise FileNotFoundError(f"No historical data found for {config.name}")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["date", "season"], na_position="last").reset_index(drop=True)
    combined.attrs.update(
        league=config.slug,
        seasons=tuple(sorted(combined["season"].astype(str).unique())),
        missing_seasons=tuple(missing),
    )
    return combined


def save_matches(matches: pd.DataFrame, path: str | Path) -> None:
    """Write a canonical frame atomically."""

    frame = _coerce_canonical(matches)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        dir=target.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        frame.to_csv(handle, index=False)
    try:
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)


def validate_matches(
    matches: pd.DataFrame,
    league: str | LeagueConfig | None = None,
    *,
    strict: bool = False,
) -> ValidationReport:
    """Check schema, fixture identity, scores, and optional full-season shape."""

    errors: list[str] = []
    warnings: list[str] = []
    missing = [column for column in CANONICAL_COLUMNS if column not in matches.columns]
    if missing:
        return ValidationReport(errors=(f"Missing canonical columns: {missing}",))

    frame = _coerce_canonical(matches)
    if frame.empty:
        errors.append("Match data is empty")
    if frame["date"].isna().any():
        errors.append(f"Invalid or missing dates: {int(frame['date'].isna().sum())}")
    missing_teams = (frame["home_team"].eq("") | frame["away_team"].eq("")).sum()
    if missing_teams:
        errors.append(f"Missing team names: {int(missing_teams)}")
    same_team = frame["home_team"].eq(frame["away_team"]).sum()
    if same_team:
        errors.append(f"Fixtures with the same home and away team: {int(same_team)}")

    home_missing = frame["home_goals"].isna()
    away_missing = frame["away_goals"].isna()
    partial_scores = home_missing.ne(away_missing).sum()
    if partial_scores:
        errors.append(f"Fixtures with only one score: {int(partial_scores)}")
    for column in ("home_goals", "away_goals"):
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = values.notna() & ((values < 0) | (values % 1 != 0))
        if invalid.any():
            errors.append(f"Invalid {column}: {int(invalid.sum())}")

    duplicate_keys = ["league", "season", "home_team", "away_team"]
    duplicates = frame.duplicated(duplicate_keys, keep=False).sum()
    if duplicates:
        errors.append(f"Duplicate home/away fixtures: {int(duplicates)} rows")

    played = frame["home_goals"].notna() & frame["away_goals"].notna()
    wrong_played_status = played & frame["status"].ne("played")
    if wrong_played_status.any():
        warnings.append(
            f"Played fixtures with a non-played status: {int(wrong_played_status.sum())}"
        )

    config = get_league(league) if league is not None else None
    if config is not None and not frame.empty:
        observed_leagues = set(frame["league"].dropna().astype(str))
        if observed_leagues - {config.slug}:
            errors.append(f"Unexpected league values: {sorted(observed_leagues)}")
        for code, season_frame in frame.groupby("season", dropna=False):
            teams = set(season_frame["home_team"]).union(season_frame["away_team"])
            teams.discard("")
            if len(teams) != config.team_count:
                message = (
                    f"{code} has {len(teams)} of {config.team_count} expected teams"
                )
                (errors if strict else warnings).append(message)
            if len(season_frame) != config.expected_matches:
                message = (
                    f"{code} has {len(season_frame)} of "
                    f"{config.expected_matches} expected fixtures"
                )
                (errors if strict else warnings).append(message)

    observed_teams = set(frame["home_team"]).union(frame["away_team"])
    observed_teams.discard("")
    stats = {
        "matches": int(len(frame)),
        "played": int(played.sum()),
        "scheduled": int((~played).sum()),
        "teams": int(len(observed_teams)),
    }
    return ValidationReport(tuple(errors), tuple(warnings), stats)


def split_played_scheduled(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = _coerce_canonical(matches)
    played_mask = frame["home_goals"].notna() & frame["away_goals"].notna()
    return frame.loc[played_mask].copy(), frame.loc[~played_mask].copy()


def season_rollover(
    previous_matches: pd.DataFrame,
    current_matches: pd.DataFrame | None = None,
    *,
    current_teams: Iterable[str] | None = None,
    league: str | LeagueConfig | None = None,
) -> SeasonRollover:
    previous = _teams(previous_matches)
    if current_teams is not None:
        current = {
            normalize_team(team, league) if league is not None else str(team).strip()
            for team in current_teams
        }
    elif current_matches is not None:
        current = _teams(current_matches)
    else:
        raise ValueError("Provide current_matches or current_teams")
    return SeasonRollover(
        returning=tuple(sorted(previous & current)),
        promoted=tuple(sorted(current - previous)),
        relegated=tuple(sorted(previous - current)),
    )


def _teams(matches: pd.DataFrame) -> set[str]:
    if {"home_team", "away_team"}.issubset(matches.columns):
        return set(matches["home_team"].dropna().astype(str)).union(
            matches["away_team"].dropna().astype(str)
        )
    if {"HomeTeam", "AwayTeam"}.issubset(matches.columns):
        return set(matches["HomeTeam"].dropna().astype(str)).union(
            matches["AwayTeam"].dropna().astype(str)
        )
    raise DataValidationError("Could not find team columns")


def _from_football_data(
    source: bytes | str | Path,
    config: LeagueConfig,
    code: str,
) -> pd.DataFrame:
    if isinstance(source, bytes):
        raw = pd.read_csv(BytesIO(source))
    else:
        raw = pd.read_csv(source)
    missing = [column for column in _RAW_REQUIRED if column not in raw.columns]
    if missing:
        raise DataValidationError(f"football-data response is missing columns: {missing}")
    date = pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce")
    home_goals = pd.to_numeric(raw["FTHG"], errors="coerce").astype("Int64")
    away_goals = pd.to_numeric(raw["FTAG"], errors="coerce").astype("Int64")
    played = home_goals.notna() & away_goals.notna()
    updated = datetime.now(timezone.utc).isoformat()
    frame = pd.DataFrame(
        {
            "league": config.slug,
            "season": code,
            "date": date,
            "home_team": raw["HomeTeam"].map(lambda team: normalize_team(team, config)),
            "away_team": raw["AwayTeam"].map(lambda team: normalize_team(team, config)),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "status": played.map({True: "played", False: "scheduled"}),
            "source_updated_at": updated,
        }
    )
    return _coerce_canonical(frame)


def _coerce_canonical(matches: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in CANONICAL_COLUMNS if column not in matches.columns]
    if missing:
        raise DataValidationError(f"Missing canonical columns: {missing}")
    frame = matches.loc[:, CANONICAL_COLUMNS].copy()
    frame["league"] = frame["league"].fillna("").astype(str).str.strip()
    frame["season"] = frame["season"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    frame["date"] = pd.to_datetime(
        frame["date"], errors="coerce", utc=True
    ).dt.tz_convert(None)
    frame["home_team"] = [
        _normalize_team_text(team, league)
        for team, league in zip(frame["home_team"], frame["league"])
    ]
    frame["away_team"] = [
        _normalize_team_text(team, league)
        for team, league in zip(frame["away_team"], frame["league"])
    ]
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce").astype("Int64")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce").astype("Int64")
    frame["status"] = frame["status"].fillna("").astype(str).str.strip().str.lower()
    frame["source_updated_at"] = pd.to_datetime(
        frame["source_updated_at"], errors="coerce", utc=True
    )
    return frame


def _load_first_available(
    candidates: Iterable[Path],
    config: LeagueConfig,
    code: str,
) -> pd.DataFrame | None:
    for path in candidates:
        if not path.exists():
            continue
        try:
            columns = set(pd.read_csv(path, nrows=0).columns)
            if set(CANONICAL_COLUMNS).issubset(columns):
                frame = _coerce_canonical(pd.read_csv(path))
            else:
                frame = _from_football_data(path, config, code)
            report = validate_matches(frame, config)
            if report.valid:
                return frame
        except (OSError, ValueError, pd.errors.ParserError):
            continue
    return None


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _with_source(
    matches: pd.DataFrame,
    source: str,
    **metadata: object,
) -> pd.DataFrame:
    frame = matches.copy()
    frame.attrs.update(data_source=source, **metadata)
    return frame
