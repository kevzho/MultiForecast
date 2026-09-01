"""League table construction and configurable ranking rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


@dataclass
class TableRow:
    team: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    away_goals: int = 0
    away_wins: int = 0
    form: list[str] = field(default_factory=list)
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def copy(self) -> "TableRow":
        return TableRow(
            team=self.team,
            played=self.played,
            wins=self.wins,
            draws=self.draws,
            losses=self.losses,
            goals_for=self.goals_for,
            goals_against=self.goals_against,
            points=self.points,
            away_goals=self.away_goals,
            away_wins=self.away_wins,
            form=list(self.form),
            extra=dict(self.extra),
        )

    def to_dict(self, *, position: int | None = None) -> dict[str, Any]:
        record = asdict(self)
        record["goal_difference"] = self.goal_difference
        if position is not None:
            record = {"position": position, **record}
        return record


Table = dict[str, TableRow]


_HOME_KEYS = ("home_team", "HomeTeam", "home", "Home", "team_home")
_AWAY_KEYS = ("away_team", "AwayTeam", "away", "Away", "team_away")
_HOME_GOAL_KEYS = ("home_goals", "FTHG", "hg", "home_score")
_AWAY_GOAL_KEYS = ("away_goals", "FTAG", "ag", "away_score")


def _record_value(record: Any, keys: Sequence[str], default: Any = None) -> Any:
    if isinstance(record, Mapping):
        for key in keys:
            if key in record:
                return record[key]
    for key in keys:
        if hasattr(record, key):
            return getattr(record, key)
    return default


def _records(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        return list(value.to_dict(orient="records"))
    if isinstance(value, Mapping):
        return [value]
    return list(value)


def _valid_goal(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def get_match_teams(match: Any) -> tuple[str, str]:
    home = _record_value(match, _HOME_KEYS)
    away = _record_value(match, _AWAY_KEYS)
    if home is None or away is None:
        raise ValueError("Match is missing home_team or away_team")
    home_name, away_name = str(home).strip(), str(away).strip()
    if not home_name or not away_name or home_name == away_name:
        raise ValueError(f"Invalid fixture: {home!r} vs {away!r}")
    return home_name, away_name


def get_match_score(match: Any) -> tuple[int, int] | None:
    home_goals = _record_value(match, _HOME_GOAL_KEYS)
    away_goals = _record_value(match, _AWAY_GOAL_KEYS)
    if not (_valid_goal(home_goals) and _valid_goal(away_goals)):
        return None
    home_score, away_score = int(float(home_goals)), int(float(away_goals))
    if home_score < 0 or away_score < 0:
        raise ValueError("Goals cannot be negative")
    return home_score, away_score


def match_is_played(match: Any) -> bool:
    return get_match_score(match) is not None


def empty_table(teams: Iterable[str]) -> Table:
    names = [str(team).strip() for team in teams]
    if any(not team for team in names):
        raise ValueError("Team names cannot be blank")
    if len(names) != len(set(names)):
        raise ValueError("Team names must be unique")
    return {team: TableRow(team=team) for team in names}


def apply_result(
    table: MutableMapping[str, TableRow],
    home_team: str,
    away_team: str,
    home_goals: int,
    away_goals: int,
    *,
    points_for_win: int = 3,
    form_size: int = 5,
) -> None:
    if home_team not in table or away_team not in table:
        missing = [team for team in (home_team, away_team) if team not in table]
        raise KeyError(f"Teams missing from table: {missing}")
    if home_goals < 0 or away_goals < 0:
        raise ValueError("Goals cannot be negative")

    home, away = table[home_team], table[away_team]
    home.played += 1
    away.played += 1
    home.goals_for += home_goals
    home.goals_against += away_goals
    away.goals_for += away_goals
    away.goals_against += home_goals
    away.away_goals += away_goals

    if home_goals > away_goals:
        home.wins += 1
        away.losses += 1
        home.points += points_for_win
        home_result, away_result = "W", "L"
    elif home_goals < away_goals:
        away.wins += 1
        away.away_wins += 1
        home.losses += 1
        away.points += points_for_win
        home_result, away_result = "L", "W"
    else:
        home.draws += 1
        away.draws += 1
        home.points += 1
        away.points += 1
        home_result = away_result = "D"

    if form_size > 0:
        home.form = (home.form + [home_result])[-form_size:]
        away.form = (away.form + [away_result])[-form_size:]


def build_table(
    results: Any,
    teams: Iterable[str] | None = None,
    *,
    points_for_win: int = 3,
    form_size: int = 5,
) -> Table:
    matches = _records(results)
    if teams is None:
        discovered: set[str] = set()
        for match in matches:
            home, away = get_match_teams(match)
            discovered.update((home, away))
        teams = sorted(discovered)

    table = empty_table(teams)
    for match in matches:
        score = get_match_score(match)
        if score is None:
            continue
        home, away = get_match_teams(match)
        apply_result(
            table,
            home,
            away,
            score[0],
            score[1],
            points_for_win=points_for_win,
            form_size=form_size,
        )
    return table


def copy_table(table: Mapping[str, TableRow | Mapping[str, Any]]) -> Table:
    copied: Table = {}
    for team, value in table.items():
        if isinstance(value, TableRow):
            row = value.copy()
        else:
            aliases = {
                "gf": "goals_for",
                "ga": "goals_against",
                "gd": "goal_difference",
                "last5": "form",
            }
            raw = {aliases.get(key, key): item for key, item in value.items()}
            row = TableRow(
                team=str(raw.get("team", team)),
                played=int(raw.get("played", raw.get("matches_played", 0))),
                wins=int(raw.get("wins", 0)),
                draws=int(raw.get("draws", 0)),
                losses=int(raw.get("losses", 0)),
                goals_for=int(raw.get("goals_for", 0)),
                goals_against=int(raw.get("goals_against", 0)),
                points=int(raw.get("points", 0)),
                away_goals=int(raw.get("away_goals", 0)),
                away_wins=int(raw.get("away_wins", 0)),
                form=list(raw.get("form", [])),
                extra=dict(raw.get("extra", {})),
            )
        row.team = str(team)
        copied[str(team)] = row
    return copied


def _criterion_name(criterion: Any) -> tuple[str, bool]:
    if isinstance(criterion, str):
        name = criterion
        descending = True
        if name.startswith("-"):
            name, descending = name[1:], False
    elif isinstance(criterion, Mapping):
        name = str(criterion.get("field", criterion.get("name", "")))
        direction = str(criterion.get("direction", "desc")).lower()
        descending = direction not in {"asc", "ascending", "lowest"}
    else:
        name = str(getattr(criterion, "field", getattr(criterion, "name", criterion)))
        direction = str(getattr(criterion, "direction", "desc")).lower()
        descending = direction not in {"asc", "ascending", "lowest"}

    aliases = {
        "pts": "points",
        "gd": "goal_difference",
        "gf": "goals_for",
        "h2h_points": "head_to_head_points",
        "h2h_goal_difference": "head_to_head_goal_difference",
        "h2h_goals_for": "head_to_head_goals_for",
        "alphabetical": "team",
    }
    name = aliases.get(name.lower().strip(), name.lower().strip())
    if name in {"fair_play", "disciplinary_points", "team"} and not (
        isinstance(criterion, Mapping) and "direction" in criterion
    ):
        descending = False
    return name, descending


def _head_to_head_table(
    teams: Sequence[str],
    results: Sequence[tuple[str, str, int, int]],
    *,
    points_for_win: int,
) -> Table:
    selected = set(teams)
    table = empty_table(teams)
    for home, away, home_goals, away_goals in results:
        if home in selected and away in selected:
            apply_result(
                table,
                home,
                away,
                home_goals,
                away_goals,
                points_for_win=points_for_win,
                form_size=0,
            )
    return table


def _played_scores(results: Sequence[Any]) -> list[tuple[str, str, int, int]]:
    scores = []
    for match in results:
        score = get_match_score(match)
        if score is not None:
            home, away = get_match_teams(match)
            scores.append((home, away, score[0], score[1]))
    return scores


def _criterion_value(
    team: str,
    name: str,
    table: Mapping[str, TableRow],
    head_to_head: Mapping[str, TableRow] | None,
) -> Any:
    row = table[team]
    if name.startswith("head_to_head_"):
        h2h = head_to_head[team] if head_to_head is not None else TableRow(team)
        name = name.removeprefix("head_to_head_")
        row = h2h
    if name == "team":
        return team.casefold()
    if name == "goal_difference":
        return row.goal_difference
    if hasattr(row, name):
        return getattr(row, name)
    return row.extra.get(name, 0.0)


def rank_table(
    table: Mapping[str, TableRow | Mapping[str, Any]],
    tiebreakers: Sequence[Any] = ("points", "goal_difference", "goals_for"),
    *,
    results: Any = (),
    points_for_win: int = 3,
) -> list[TableRow]:
    rows = copy_table(table)
    criteria = list(tiebreakers) or ["points", "goal_difference", "goals_for"]
    has_head_to_head = any(
        _criterion_name(criterion)[0].startswith("head_to_head_")
        for criterion in criteria
    )
    played_scores = _played_scores(_records(results)) if has_head_to_head else []
    groups: list[list[str]] = [sorted(rows, key=str.casefold)]
    head_to_head_cache: dict[frozenset[str], Table] = {}
    for raw_criterion in criteria:
        name, descending = _criterion_name(raw_criterion)
        next_groups: list[list[str]] = []
        for group in groups:
            if len(group) < 2:
                next_groups.append(group)
                continue
            h2h = None
            if name.startswith("head_to_head_"):
                cache_key = frozenset(group)
                if cache_key not in head_to_head_cache:
                    head_to_head_cache[cache_key] = _head_to_head_table(
                        group,
                        played_scores,
                        points_for_win=points_for_win,
                    )
                h2h = head_to_head_cache[cache_key]
            buckets: dict[Any, list[str]] = {}
            for team in group:
                value = _criterion_value(team, name, rows, h2h)
                buckets.setdefault(value, []).append(team)
            ordered_values = sorted(buckets, reverse=descending)
            for value in ordered_values:
                next_groups.append(sorted(buckets[value], key=str.casefold))
        groups = next_groups

    return [rows[team] for group in groups for team in group]


def table_as_records(
    table: Mapping[str, TableRow | Mapping[str, Any]] | Sequence[TableRow],
    *,
    ranked: bool = False,
    tiebreakers: Sequence[Any] = ("points", "goal_difference", "goals_for"),
    results: Any = (),
    points_for_win: int = 3,
) -> list[dict[str, Any]]:
    if isinstance(table, Mapping):
        rows = (
            rank_table(
                table,
                tiebreakers,
                results=results,
                points_for_win=points_for_win,
            )
            if ranked
            else list(copy_table(table).values())
        )
    else:
        rows = [row.copy() for row in table]
    return [row.to_dict(position=index) for index, row in enumerate(rows, start=1)]


__all__ = [
    "Table",
    "TableRow",
    "apply_result",
    "build_table",
    "copy_table",
    "empty_table",
    "get_match_score",
    "get_match_teams",
    "match_is_played",
    "rank_table",
    "table_as_records",
]
