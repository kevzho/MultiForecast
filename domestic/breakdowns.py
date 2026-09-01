"""Structured match previews from domestic scoreline models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, Sequence

import numpy as np

from domestic.simulation import _model_name, _predict, _validated_grid
from domestic.standings import get_match_score, get_match_teams


@dataclass(frozen=True)
class MatchBreakdown:
    home_team: str
    away_team: str
    model: str
    probabilities: dict[str, float]
    expected_goals: dict[str, float]
    top_scorelines: tuple[dict[str, Any], ...]
    goal_markets: dict[str, Any]
    team_strengths: dict[str, dict[str, Any]]
    recent_form: dict[str, dict[str, Any]]
    model_comparison: dict[str, dict[str, Any]]
    confidence: dict[str, Any]
    season_impact: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["top_scorelines"] = list(self.top_scorelines)
        return value


def _records(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        return list(value.to_dict(orient="records"))
    if isinstance(value, Mapping):
        return [value]
    return list(value)


def _distribution_summary(distribution: Any) -> dict[str, Any]:
    grid = _validated_grid(distribution)
    p_home = float(np.tril(grid, k=-1).sum())
    p_draw = float(np.trace(grid))
    p_away = float(np.triu(grid, k=1).sum())
    home_axis = np.arange(grid.shape[0], dtype=float)[:, None]
    away_axis = np.arange(grid.shape[1], dtype=float)[None, :]
    xg_home = float((grid * home_axis).sum())
    xg_away = float((grid * away_axis).sum())
    return {
        "grid": grid,
        "probabilities": {
            "home_win": p_home,
            "draw": p_draw,
            "away_win": p_away,
        },
        "expected_goals": {
            "home": xg_home,
            "away": xg_away,
            "total": xg_home + xg_away,
        },
    }


def _top_scorelines(grid: np.ndarray, limit: int) -> tuple[dict[str, Any], ...]:
    limit = max(1, min(int(limit), grid.size))
    indexes = np.argsort(grid, axis=None)[::-1][:limit]
    output = []
    for index in indexes:
        home_goals, away_goals = np.unravel_index(int(index), grid.shape)
        output.append(
            {
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "score": f"{home_goals}-{away_goals}",
                "probability": float(grid[home_goals, away_goals]),
            }
        )
    return tuple(output)


def _goal_markets(grid: np.ndarray) -> dict[str, Any]:
    totals = np.add.outer(np.arange(grid.shape[0]), np.arange(grid.shape[1]))
    under_2_5 = float(grid[totals <= 2].sum())
    btts_yes = float(grid[1:, 1:].sum())
    home_clean_sheet = float(grid[:, 0].sum())
    away_clean_sheet = float(grid[0, :].sum())
    return {
        "over_under_2_5": {
            "over": 1.0 - under_2_5,
            "under": under_2_5,
        },
        "both_teams_to_score": {
            "yes": btts_yes,
            "no": 1.0 - btts_yes,
        },
        "clean_sheet": {
            "home": home_clean_sheet,
            "away": away_clean_sheet,
            "neither": float(grid[1:, 1:].sum()),
        },
    }


def _serialize_strength(value: Any) -> dict[str, Any]:
    if value is None:
        return {"rating": None, "attack": None, "defense": None}
    if isinstance(value, (int, float, np.number)):
        return {"rating": float(value), "attack": None, "defense": None}
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    elif hasattr(value, "__dict__"):
        value = vars(value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        aliases = {
            "elo": "rating",
            "elo_rating": "rating",
            "attack_strength": "attack",
            "defence_strength": "defense",
            "defense_strength": "defense",
        }
        for key, item in value.items():
            name = aliases.get(str(key), str(key))
            if isinstance(item, np.generic):
                item = item.item()
            output[name] = item
        output.setdefault("rating", None)
        output.setdefault("attack", None)
        output.setdefault("defense", None)
        return output
    return {"rating": None, "attack": None, "defense": None, "value": str(value)}


def _lookup_strength(source: Any, team: str) -> Any:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(team)
    for method_name in ("team_strength", "get_team", "get"):
        method = getattr(source, method_name, None)
        if callable(method):
            try:
                return method(team)
            except (KeyError, TypeError):
                pass
    ratings = getattr(source, "ratings", None)
    if isinstance(ratings, Mapping):
        return ratings.get(team)
    attack = getattr(source, "attack", None)
    defense = getattr(source, "defense", None)
    if isinstance(attack, Mapping) or isinstance(defense, Mapping):
        return {
            "attack": attack.get(team) if isinstance(attack, Mapping) else None,
            "defense": defense.get(team) if isinstance(defense, Mapping) else None,
        }
    return None


def _team_strengths(
    model: Any,
    supplied: Any,
    home: str,
    away: str,
) -> dict[str, dict[str, Any]]:
    source = supplied
    if source is None:
        source = getattr(model, "ratings", None)
    if source is None:
        source = getattr(model, "strengths", None)
    return {
        "home": {"team": home, **_serialize_strength(_lookup_strength(source, home))},
        "away": {"team": away, **_serialize_strength(_lookup_strength(source, away))},
    }


def _form_for_team(results: Sequence[Any], team: str, window: int) -> dict[str, Any]:
    matches: list[tuple[str, int, int]] = []
    for match in results:
        score = get_match_score(match)
        if score is None:
            continue
        home, away = get_match_teams(match)
        if team == home:
            goals_for, goals_against = score
        elif team == away:
            goals_for, goals_against = score[1], score[0]
        else:
            continue
        if goals_for > goals_against:
            result = "W"
        elif goals_for < goals_against:
            result = "L"
        else:
            result = "D"
        matches.append((result, goals_for, goals_against))

    sample = matches[-max(1, window) :]
    wins = sum(result == "W" for result, _, _ in sample)
    draws = sum(result == "D" for result, _, _ in sample)
    losses = sum(result == "L" for result, _, _ in sample)
    points = wins * 3 + draws
    return {
        "matches": len(sample),
        "sequence": [result for result, _, _ in sample],
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": sum(gf for _, gf, _ in sample),
        "goals_against": sum(ga for _, _, ga in sample),
        "points_per_game": points / len(sample) if sample else None,
    }


def _comparison(
    home: str,
    away: str,
    primary_model: Any,
    comparison_models: Mapping[str, Any] | Sequence[Any] | None,
) -> dict[str, dict[str, Any]]:
    models: dict[str, Any] = {_model_name(primary_model): primary_model}
    if isinstance(comparison_models, Mapping):
        models.update({str(name): model for name, model in comparison_models.items()})
    elif comparison_models:
        models.update({_model_name(model): model for model in comparison_models})

    output = {}
    for name, model in models.items():
        summary = _distribution_summary(_predict(model, home, away))
        output[name] = {
            "probabilities": summary["probabilities"],
            "expected_goals": summary["expected_goals"],
        }
    return output


def _calibration_details(calibration: Any, model_name: str) -> dict[str, Any]:
    if calibration is None:
        return {"status": "not_available", "error": None, "sample_size": None}
    value = calibration
    if isinstance(calibration, Mapping) and model_name in calibration:
        value = calibration[model_name]
    if isinstance(value, (int, float, np.number)):
        error = float(value)
        sample_size = None
    elif isinstance(value, Mapping):
        raw_error = value.get(
            "calibration_error",
            value.get("expected_calibration_error", value.get("ece")),
        )
        error = float(raw_error) if raw_error is not None else None
        sample_size = value.get("sample_size", value.get("n"))
    else:
        error, sample_size = None, None

    if error is None:
        status = "not_available"
    elif error <= 0.04:
        status = "well_calibrated"
    elif error <= 0.08:
        status = "acceptable"
    else:
        status = "needs_review"
    return {"status": status, "error": error, "sample_size": sample_size}


def _confidence(probabilities: Mapping[str, float], calibration: Any, model: str) -> dict[str, Any]:
    values = np.asarray(list(probabilities.values()), dtype=float)
    positive = values[values > 0]
    entropy = -float(np.sum(positive * np.log(positive)))
    certainty = 1.0 - entropy / math.log(len(values))
    peak = float(values.max())
    if peak >= 0.65:
        level = "high"
    elif peak >= 0.50:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "score": certainty,
        "highest_outcome_probability": peak,
        "calibration": _calibration_details(calibration, model),
    }


def _forecast_teams(forecast: Any) -> Mapping[str, Any]:
    if forecast is None:
        return {}
    if hasattr(forecast, "teams"):
        return forecast.teams
    if isinstance(forecast, Mapping):
        return forecast.get("teams", forecast.get("per_team", forecast))
    return {}


def _forecast_metrics(forecast: Any, team: str) -> dict[str, float] | None:
    value = _forecast_teams(forecast).get(team)
    if value is None:
        return None
    keys = (
        "title_probability",
        "europe_probability",
        "relegation_probability",
        "playoff_probability",
        "expected_points",
        "expected_position",
    )
    output = {}
    for key in keys:
        if isinstance(value, Mapping):
            raw = value.get(key)
        else:
            raw = getattr(value, key, None)
        if raw is not None:
            output[key] = float(raw)
    return output


def _season_impact(
    home: str,
    away: str,
    season_forecast: Any,
    outcome_forecasts: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not outcome_forecasts:
        return None
    aliases = {
        "h": "home_win",
        "home": "home_win",
        "home_win": "home_win",
        "d": "draw",
        "draw": "draw",
        "a": "away_win",
        "away": "away_win",
        "away_win": "away_win",
    }
    normalized = {
        aliases.get(str(name).lower(), str(name).lower()): forecast
        for name, forecast in outcome_forecasts.items()
        if str(name).lower() not in {"baseline", "current"}
    }
    baseline = season_forecast or outcome_forecasts.get("baseline") or outcome_forecasts.get("current")
    output: dict[str, Any] = {}
    for team in (home, away):
        outcomes = {
            outcome: metrics
            for outcome, forecast in normalized.items()
            if (metrics := _forecast_metrics(forecast, team)) is not None
        }
        if not outcomes:
            continue
        metric_names = sorted({key for metrics in outcomes.values() for key in metrics})
        swing = {}
        for metric in metric_names:
            values = [metrics[metric] for metrics in outcomes.values() if metric in metrics]
            if values:
                swing[metric] = max(values) - min(values)
        baseline_metrics = _forecast_metrics(baseline, team)
        deltas = None
        if baseline_metrics:
            deltas = {
                outcome: {
                    metric: value - baseline_metrics[metric]
                    for metric, value in metrics.items()
                    if metric in baseline_metrics
                }
                for outcome, metrics in outcomes.items()
            }
        output[team] = {
            "outcomes": outcomes,
            "swing": swing,
            "change_from_baseline": deltas,
        }
    return output or None


def build_match_breakdown(
    fixture: Any,
    model: Any,
    *,
    comparison_models: Mapping[str, Any] | Sequence[Any] | None = None,
    results: Any = (),
    strengths: Any = None,
    calibration: Any = None,
    season_forecast: Any = None,
    outcome_forecasts: Mapping[str, Any] | None = None,
    top_scoreline_count: int = 5,
    form_window: int = 5,
) -> MatchBreakdown:
    home, away = get_match_teams(fixture)
    distribution = _predict(model, home, away)
    summary = _distribution_summary(distribution)
    grid = summary["grid"]
    model_name = _model_name(model)
    result_rows = _records(results)

    return MatchBreakdown(
        home_team=home,
        away_team=away,
        model=model_name,
        probabilities=summary["probabilities"],
        expected_goals=summary["expected_goals"],
        top_scorelines=_top_scorelines(grid, top_scoreline_count),
        goal_markets=_goal_markets(grid),
        team_strengths=_team_strengths(model, strengths, home, away),
        recent_form={
            "home": {"team": home, **_form_for_team(result_rows, home, form_window)},
            "away": {"team": away, **_form_for_team(result_rows, away, form_window)},
        },
        model_comparison=_comparison(home, away, model, comparison_models),
        confidence=_confidence(summary["probabilities"], calibration, model_name),
        season_impact=_season_impact(
            home,
            away,
            season_forecast,
            outcome_forecasts,
        ),
    )


def build_match_breakdowns(
    fixtures: Any,
    model: Any,
    **kwargs: Any,
) -> list[MatchBreakdown]:
    return [
        build_match_breakdown(fixture, model, **kwargs)
        for fixture in _records(fixtures)
    ]


__all__ = ["MatchBreakdown", "build_match_breakdown", "build_match_breakdowns"]
