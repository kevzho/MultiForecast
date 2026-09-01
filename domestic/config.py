"""League and storage configuration for domestic competitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


DEFAULT_SEASON = "2627"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"


@dataclass(frozen=True, slots=True)
class LeagueConfig:
    """Rules and model defaults for one domestic league."""

    slug: str
    name: str
    country: str
    code: str
    team_count: int
    season: str = DEFAULT_SEASON
    rounds: int = 2
    points_for_win: int = 3
    home_advantage: float = 70.0
    draw_rate: float = 0.26
    avg_goals: float = 2.65
    standings_tiebreakers: tuple[str, ...] = (
        "points",
        "goal_difference",
        "goals_for",
    )
    champions_league_positions: tuple[int, ...] = (1, 2, 3, 4)
    europa_league_positions: tuple[int, ...] = (5,)
    conference_league_positions: tuple[int, ...] = (6,)
    relegation_positions: tuple[int, ...] = (18, 19, 20)
    relegation_playoff_positions: tuple[int, ...] = ()
    qualification_note: str = (
        "Cup winners and UEFA performance places can change the final allocation."
    )

    @property
    def matches_per_team(self) -> int:
        return (self.team_count - 1) * self.rounds

    @property
    def expected_matches(self) -> int:
        return self.team_count * self.matches_per_team // 2

    @property
    def league_id(self) -> str:
        return self.slug

    @property
    def football_data_code(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class DataPaths:
    raw: Path
    processed: Path
    last_known_good: Path

    def create_parents(self) -> None:
        self.raw.parent.mkdir(parents=True, exist_ok=True)
        self.processed.parent.mkdir(parents=True, exist_ok=True)
        self.last_known_good.parent.mkdir(parents=True, exist_ok=True)


LEAGUES: dict[str, LeagueConfig] = {
    "premier_league": LeagueConfig(
        slug="premier_league",
        name="Premier League",
        country="England",
        code="E0",
        team_count=20,
        home_advantage=68.0,
        draw_rate=0.255,
        avg_goals=2.78,
        standings_tiebreakers=(
            "points",
            "goal_difference",
            "goals_for",
        ),
    ),
    "serie_a": LeagueConfig(
        slug="serie_a",
        name="Serie A",
        country="Italy",
        code="I1",
        team_count=20,
        home_advantage=62.0,
        draw_rate=0.265,
        avg_goals=2.60,
        standings_tiebreakers=(
            "points",
            "head_to_head_points",
            "head_to_head_goal_difference",
            "goal_difference",
            "goals_for",
        ),
        qualification_note=(
            "Title and relegation ties may require a playoff; cup winners and UEFA "
            "performance places can change the allocation."
        ),
    ),
    "ligue_1": LeagueConfig(
        slug="ligue_1",
        name="Ligue 1",
        country="France",
        code="F1",
        team_count=18,
        home_advantage=64.0,
        draw_rate=0.245,
        avg_goals=2.70,
        standings_tiebreakers=(
            "points",
            "goal_difference",
            "goals_for",
            "head_to_head_points",
        ),
        relegation_positions=(17, 18),
        relegation_playoff_positions=(16,),
    ),
    "la_liga": LeagueConfig(
        slug="la_liga",
        name="La Liga",
        country="Spain",
        code="SP1",
        team_count=20,
        home_advantage=68.0,
        draw_rate=0.265,
        avg_goals=2.55,
        standings_tiebreakers=(
            "points",
            "head_to_head_points",
            "head_to_head_goal_difference",
            "goal_difference",
            "goals_for",
        ),
    ),
    "bundesliga": LeagueConfig(
        slug="bundesliga",
        name="Bundesliga",
        country="Germany",
        code="D1",
        team_count=18,
        home_advantage=65.0,
        draw_rate=0.235,
        avg_goals=3.05,
        standings_tiebreakers=(
            "points",
            "goal_difference",
            "goals_for",
            "head_to_head_points",
            "head_to_head_away_goals",
            "away_goals",
        ),
        relegation_positions=(17, 18),
        relegation_playoff_positions=(16,),
    ),
}


_LEAGUE_ALIASES = {
    "e0": "premier_league",
    "england": "premier_league",
    "english_premier_league": "premier_league",
    "pl": "premier_league",
    "premierleague": "premier_league",
    "i1": "serie_a",
    "italy": "serie_a",
    "seriea": "serie_a",
    "f1": "ligue_1",
    "france": "ligue_1",
    "ligue1": "ligue_1",
    "sp1": "la_liga",
    "spain": "la_liga",
    "laliga": "la_liga",
    "d1": "bundesliga",
    "germany": "bundesliga",
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def get_league(value: str | LeagueConfig) -> LeagueConfig:
    """Resolve a slug, name, country, or football-data code."""

    if isinstance(value, LeagueConfig):
        return value
    key = _key(value)
    key = _LEAGUE_ALIASES.get(key, key)
    try:
        return LEAGUES[key]
    except KeyError as exc:
        supported = ", ".join(config.slug for config in LEAGUES.values())
        raise KeyError(f"Unknown league {value!r}. Supported leagues: {supported}") from exc


def list_leagues() -> tuple[LeagueConfig, ...]:
    return tuple(LEAGUES.values())


def season_code(value: str | int) -> str:
    """Return the football-data four-digit season code."""

    text = str(value).strip().replace("/", "").replace("-", "")
    if len(text) == 6 and text.isdigit():
        first, second = int(text[:4]), int(text[4:])
        if second != (first + 1) % 100:
            raise ValueError(f"Season must span consecutive years: {value!r}")
        return f"{first % 100:02d}{second:02d}"
    if len(text) == 8 and text.isdigit():
        first, second = int(text[:4]), int(text[4:])
        if second != first + 1:
            raise ValueError(f"Season must span consecutive years: {value!r}")
        return f"{first % 100:02d}{second % 100:02d}"
    if len(text) != 4 or not text.isdigit():
        raise ValueError(f"Expected a season such as '2627' or '2026/27': {value!r}")
    first, second = int(text[:2]), int(text[2:])
    if second != (first + 1) % 100:
        raise ValueError(f"Season must span consecutive years: {value!r}")
    return text


def previous_season_codes(season: str | int, count: int = 5) -> tuple[str, ...]:
    if count < 0:
        raise ValueError("count must be non-negative")
    current = season_code(season)
    start = int(current[:2])
    return tuple(
        f"{(start - offset) % 100:02d}{(start - offset + 1) % 100:02d}"
        for offset in range(count, -1, -1)
    )


def data_paths(
    league: str | LeagueConfig,
    season: str | int | None = None,
    data_root: str | Path = DEFAULT_DATA_ROOT,
) -> DataPaths:
    config = get_league(league)
    code = season_code(season or config.season)
    root = Path(data_root)
    base = root / "domestic"
    return DataPaths(
        raw=base / "raw" / code / f"{config.code}.csv",
        processed=base / "processed" / code / f"{config.slug}.csv",
        last_known_good=base / "last_known_good" / code / f"{config.code}.csv",
    )
