"""Monte Carlo season simulation from scoreline distributions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from domestic.standings import (
    TableRow,
    apply_result,
    build_table,
    copy_table,
    get_match_score,
    get_match_teams,
    rank_table,
    table_as_records,
)


@dataclass(frozen=True)
class TeamSeasonForecast:
    team: str
    title_probability: float
    europe_probability: float
    qualification_probabilities: dict[str, float]
    relegation_probability: float
    playoff_probability: float
    expected_points: float
    expected_position: float
    expected_goals_for: float
    expected_goals_against: float
    position_probabilities: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["position_probabilities"] = list(self.position_probabilities)
        return value


@dataclass(frozen=True)
class SeasonForecast:
    league: str | None
    season: str | None
    model: str
    simulations: int
    seed: int | None
    team_count: int
    remaining_fixtures: int
    standings_tiebreakers: tuple[str, ...]
    qualification_positions: dict[str, tuple[int, ...]]
    relegation_positions: tuple[int, ...]
    playoff_positions: tuple[int, ...]
    current_table: tuple[dict[str, Any], ...]
    teams: dict[str, TeamSeasonForecast]

    def to_dict(self) -> dict[str, Any]:
        return {
            "league": self.league,
            "season": self.season,
            "model": self.model,
            "simulations": self.simulations,
            "seed": self.seed,
            "team_count": self.team_count,
            "remaining_fixtures": self.remaining_fixtures,
            "standings_tiebreakers": list(self.standings_tiebreakers),
            "qualification_positions": {
                name: list(positions)
                for name, positions in self.qualification_positions.items()
            },
            "relegation_positions": list(self.relegation_positions),
            "playoff_positions": list(self.playoff_positions),
            "current_table": list(self.current_table),
            "teams": {
                team: forecast.to_dict() for team, forecast in self.teams.items()
            },
        }

    @property
    def per_team(self) -> dict[str, TeamSeasonForecast]:
        return self.teams


@dataclass(frozen=True)
class _GridDistribution:
    grid: np.ndarray


class _OutcomeConditionedModel:
    def __init__(self, model: Any, fixture: Any, outcome: str) -> None:
        self.model = model
        self.fixture = get_match_teams(fixture)
        self.outcome = outcome
        self.name = _model_name(model)

    def predict(self, home: str, away: str, *, neutral: bool = False) -> Any:
        distribution = _predict(self.model, home, away)
        if (home, away) != self.fixture:
            return distribution
        grid = _validated_grid(distribution)
        home_goals, away_goals = np.indices(grid.shape)
        if self.outcome == "home_win":
            mask = home_goals > away_goals
        elif self.outcome == "draw":
            mask = home_goals == away_goals
        else:
            mask = home_goals < away_goals
        conditioned = np.where(mask, grid, 0.0)
        mass = float(conditioned.sum())
        if mass <= 0:
            raise ValueError(f"Model gives no probability to {self.outcome}")
        return _GridDistribution(conditioned / mass)


def _records(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        return list(value.to_dict(orient="records"))
    if isinstance(value, Mapping):
        return [value]
    return list(value)


def _config_value(config: Any, name: str, default: Any = None) -> Any:
    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(name, default)
    return getattr(config, name, default)


def _model_name(model: Any) -> str:
    explicit = getattr(model, "name", None) or getattr(model, "model_name", None)
    if explicit:
        return str(explicit)
    name = model.__class__.__name__
    known = {
        "EloResultModel": "elo",
        "EloPoissonModel": "elo_poisson",
        "PoissonModel": "poisson",
        "DixonColesModel": "dixon_coles",
        "BradleyTerryModel": "bradley_terry",
        "EnsembleModel": "ensemble",
        "CalibratedEnsemble": "ensemble",
    }
    if name in known:
        return known[name]
    if name.lower().endswith("model"):
        name = name[:-5]
    output = []
    for index, char in enumerate(name):
        if char.isupper() and index and not name[index - 1].isupper():
            output.append("_")
        output.append(char.lower())
    return "".join(output) or "model"


def _match_key(match: Any) -> tuple[str, str]:
    return get_match_teams(match)


def _completed_matches(fixtures: Sequence[Any], results: Sequence[Any]) -> list[Any]:
    completed: dict[tuple[str, str], Any] = {}
    for match in fixtures:
        if get_match_score(match) is not None:
            completed[_match_key(match)] = match
    for match in results:
        if get_match_score(match) is not None:
            completed[_match_key(match)] = match
    return list(completed.values())


def _remaining_matches(fixtures: Sequence[Any], completed: Sequence[Any]) -> list[Any]:
    completed_keys = {_match_key(match) for match in completed}
    return [
        match
        for match in fixtures
        if get_match_score(match) is None and _match_key(match) not in completed_keys
    ]


def _discover_teams(
    fixtures: Sequence[Any],
    results: Sequence[Any],
    current_table: Mapping[str, Any] | None,
    teams: Iterable[str] | None,
) -> list[str]:
    discovered = {str(team) for team in (teams or [])}
    if current_table:
        discovered.update(str(team) for team in current_table)
    for match in [*fixtures, *results]:
        discovered.update(get_match_teams(match))
    if not discovered:
        raise ValueError("No teams found in fixtures, results, or current_table")
    return sorted(discovered, key=str.casefold)


def _positions(
    value: Any,
    team_count: int,
    *,
    from_bottom: bool = False,
) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (int, np.integer)):
        count = max(0, min(int(value), team_count))
        if from_bottom:
            return tuple(range(team_count - count + 1, team_count + 1))
        return tuple(range(1, count + 1))
    positions = tuple(sorted({int(position) for position in value}))
    invalid = [position for position in positions if not 1 <= position <= team_count]
    if invalid:
        raise ValueError(f"Positions outside 1..{team_count}: {invalid}")
    return positions


def _qualification_positions(
    config: Any,
    override: Mapping[str, Any] | None,
    team_count: int,
) -> dict[str, tuple[int, ...]]:
    if override is not None:
        return {
            str(name): _positions(value, team_count)
            for name, value in override.items()
        }
    fields = {
        "champions_league": "champions_league_positions",
        "europa_league": "europa_league_positions",
        "conference_league": "conference_league_positions",
    }
    return {
        name: _positions(_config_value(config, field, ()), team_count)
        for name, field in fields.items()
    }


def _predict(model: Any, home: str, away: str) -> Any:
    predict = model.predict
    try:
        signature = inspect.signature(predict)
        supports_neutral = "neutral" in signature.parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    except (TypeError, ValueError):
        supports_neutral = True
    return predict(home, away, neutral=False) if supports_neutral else predict(home, away)


def _validated_grid(distribution: Any) -> np.ndarray:
    grid = np.asarray(distribution.grid, dtype=float)
    if grid.ndim != 2 or not grid.size:
        raise ValueError("Scoreline grid must be a non-empty two-dimensional array")
    if not np.all(np.isfinite(grid)) or np.any(grid < 0):
        raise ValueError("Scoreline grid contains invalid probabilities")
    total = float(grid.sum())
    if total <= 0:
        raise ValueError("Scoreline grid has no probability mass")
    return grid / total


def _precompute_distributions(
    fixtures: Sequence[Any], model: Any
) -> list[tuple[str, str, np.ndarray]]:
    cached: dict[tuple[str, str], np.ndarray] = {}
    output = []
    for fixture in fixtures:
        home, away = get_match_teams(fixture)
        key = (home, away)
        if key not in cached:
            cached[key] = _validated_grid(_predict(model, home, away))
        output.append((home, away, cached[key]))
    return output


def _sample_fixtures(
    distributions: Sequence[tuple[str, str, np.ndarray]],
    rng: np.random.Generator,
    simulations: int,
) -> list[tuple[str, str, np.ndarray, np.ndarray]]:
    sampled = []
    for home, away, grid in distributions:
        indexes = rng.choice(grid.size, size=simulations, p=grid.ravel())
        sampled.append(
            (
                home,
                away,
                (indexes // grid.shape[1]).astype(np.int16),
                (indexes % grid.shape[1]).astype(np.int16),
            )
        )
    return sampled


def simulate_season(
    fixtures: Any,
    model: Any,
    *,
    results: Any = (),
    current_table: Mapping[str, TableRow | Mapping[str, Any]] | None = None,
    teams: Iterable[str] | None = None,
    league_config: Any = None,
    config: Any = None,
    n_simulations: int | None = None,
    n_sims: int | None = None,
    seed: int | None = None,
    qualification_slots: Mapping[str, Any] | None = None,
    relegation_slots: Any = None,
    playoff_slots: Any = None,
    tiebreakers: Sequence[str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> SeasonForecast:
    if league_config is None:
        league_config = config
    if n_simulations is None:
        n_simulations = 10_000 if n_sims is None else n_sims
    elif n_sims is not None and n_simulations != n_sims:
        raise ValueError("n_simulations and n_sims disagree")
    if n_simulations <= 0:
        raise ValueError("n_simulations must be positive")

    fixture_rows = _records(fixtures)
    result_rows = _records(results)
    completed = _completed_matches(fixture_rows, result_rows)
    remaining = _remaining_matches(fixture_rows, completed)
    team_names = _discover_teams(fixture_rows, completed, current_table, teams)
    team_count = len(team_names)
    points_for_win = int(_config_value(league_config, "points_for_win", 3))

    if current_table is None:
        base_table = build_table(
            completed,
            teams=team_names,
            points_for_win=points_for_win,
        )
    else:
        base_table = copy_table(current_table)
        missing = [team for team in team_names if team not in base_table]
        if missing:
            base_table.update(build_table((), teams=missing))

    ranking_rules = tuple(
        tiebreakers
        or _config_value(
            league_config,
            "standings_tiebreakers",
            ("points", "goal_difference", "goals_for"),
        )
    )
    qualification = _qualification_positions(
        league_config,
        qualification_slots,
        team_count,
    )
    relegation_value = (
        _config_value(league_config, "relegation_positions", ())
        if relegation_slots is None
        else relegation_slots
    )
    playoff_value = (
        _config_value(league_config, "relegation_playoff_positions", ())
        if playoff_slots is None
        else playoff_slots
    )
    relegation_positions = _positions(
        relegation_value,
        team_count,
        from_bottom=isinstance(relegation_value, (int, np.integer)),
    )
    playoff_positions = _positions(
        playoff_value,
        team_count,
        from_bottom=isinstance(playoff_value, (int, np.integer)),
    )
    european_positions = {
        position for positions in qualification.values() for position in positions
    }

    distributions = _precompute_distributions(remaining, model)
    needs_head_to_head = any("head_to_head" in rule for rule in ranking_rules)
    rng = np.random.default_rng(seed)
    sampled_fixtures = _sample_fixtures(distributions, rng, n_simulations)

    position_counts = {team: np.zeros(team_count, dtype=np.int64) for team in team_names}
    point_totals = {team: 0.0 for team in team_names}
    goals_for_totals = {team: 0.0 for team in team_names}
    goals_against_totals = {team: 0.0 for team in team_names}
    qualification_counts = {
        name: {team: 0 for team in team_names} for name in qualification
    }
    europe_counts = {team: 0 for team in team_names}
    relegation_counts = {team: 0 for team in team_names}
    playoff_counts = {team: 0 for team in team_names}

    report_every = max(1, n_simulations // 100)
    for simulation_index in range(n_simulations):
        table = copy_table(base_table)
        simulated_results: list[dict[str, Any]] = []
        for home, away, home_samples, away_samples in sampled_fixtures:
            home_goals = int(home_samples[simulation_index])
            away_goals = int(away_samples[simulation_index])
            apply_result(
                table,
                home,
                away,
                home_goals,
                away_goals,
                points_for_win=points_for_win,
                form_size=0,
            )
            if needs_head_to_head:
                simulated_results.append(
                    {
                        "home_team": home,
                        "away_team": away,
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                    }
                )

        ranking_results = [*completed, *simulated_results] if needs_head_to_head else ()
        ranked = rank_table(
            table,
            ranking_rules,
            results=ranking_results,
            points_for_win=points_for_win,
        )
        for position, row in enumerate(ranked, start=1):
            team = row.team
            position_counts[team][position - 1] += 1
            point_totals[team] += row.points
            goals_for_totals[team] += row.goals_for
            goals_against_totals[team] += row.goals_against
            if position in european_positions:
                europe_counts[team] += 1
            if position in relegation_positions:
                relegation_counts[team] += 1
            if position in playoff_positions:
                playoff_counts[team] += 1
            for name, positions in qualification.items():
                if position in positions:
                    qualification_counts[name][team] += 1

        if progress and (
            (simulation_index + 1) % report_every == 0
            or simulation_index + 1 == n_simulations
        ):
            progress(simulation_index + 1, n_simulations)

    forecasts: dict[str, TeamSeasonForecast] = {}
    for team in team_names:
        distribution = position_counts[team] / n_simulations
        forecasts[team] = TeamSeasonForecast(
            team=team,
            title_probability=float(distribution[0]),
            europe_probability=europe_counts[team] / n_simulations,
            qualification_probabilities={
                name: qualification_counts[name][team] / n_simulations
                for name in qualification
            },
            relegation_probability=relegation_counts[team] / n_simulations,
            playoff_probability=playoff_counts[team] / n_simulations,
            expected_points=point_totals[team] / n_simulations,
            expected_position=float(
                np.dot(distribution, np.arange(1, team_count + 1))
            ),
            expected_goals_for=goals_for_totals[team] / n_simulations,
            expected_goals_against=goals_against_totals[team] / n_simulations,
            position_probabilities=tuple(float(value) for value in distribution),
        )

    current_ranked = table_as_records(
        base_table,
        ranked=True,
        tiebreakers=ranking_rules,
        results=completed,
        points_for_win=points_for_win,
    )
    return SeasonForecast(
        league=_config_value(league_config, "slug", _config_value(league_config, "id")),
        season=_config_value(league_config, "season"),
        model=_model_name(model),
        simulations=n_simulations,
        seed=seed,
        team_count=team_count,
        remaining_fixtures=len(remaining),
        standings_tiebreakers=ranking_rules,
        qualification_positions=qualification,
        relegation_positions=relegation_positions,
        playoff_positions=playoff_positions,
        current_table=tuple(current_ranked),
        teams=forecasts,
    )


def simulate_fixture_outcomes(
    fixtures: Any,
    fixture: Any,
    model: Any,
    **simulation_options: Any,
) -> dict[str, SeasonForecast]:
    return {
        outcome: simulate_season(
            fixtures,
            _OutcomeConditionedModel(model, fixture, outcome),
            **simulation_options,
        )
        for outcome in ("home_win", "draw", "away_win")
    }


__all__ = [
    "SeasonForecast",
    "TeamSeasonForecast",
    "simulate_fixture_outcomes",
    "simulate_season",
]
