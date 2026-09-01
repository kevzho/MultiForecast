"""End-to-end domestic forecast orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from domestic.breakdowns import MatchBreakdown, build_match_breakdown, build_match_breakdowns
from domestic.config import DEFAULT_DATA_ROOT, LeagueConfig, get_league, previous_season_codes
from domestic.data import (
    load_history,
    load_matches,
    season_rollover,
    split_played_scheduled,
)
from domestic.models import (
    MODEL_NAMES,
    EloPoissonModel,
    EloResultModel,
    EnsembleModel,
    MatchModel,
    fit_elo_ratings,
    fit_models,
    rollover_ratings,
)
from domestic.simulation import SeasonForecast, simulate_fixture_outcomes, simulate_season
from domestic.validation import compare_models, derive_ensemble_weights, select_model


@dataclass(frozen=True)
class ForecastRun:
    config: LeagueConfig
    generated_at: str
    matches: pd.DataFrame
    training_matches: pd.DataFrame
    models: dict[str, MatchModel]
    selected_model: str
    validation: pd.DataFrame
    forecast: SeasonForecast
    breakdowns: tuple[MatchBreakdown, ...]

    @property
    def model(self) -> MatchModel:
        return self.models[self.selected_model]


def _training_seasons(config: LeagueConfig, count: int) -> tuple[str, ...]:
    codes = previous_season_codes(config.season, count)
    return tuple(code for code in codes if code != config.season)


def load_training_matches(
    league: str | LeagueConfig,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    history_seasons: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = get_league(league)
    current = load_matches(config, data_root=data_root)
    history = load_history(
        config,
        seasons=_training_seasons(config, history_seasons),
        data_root=data_root,
        require_all=False,
    )
    training = pd.concat([history, current], ignore_index=True)
    training = training.drop_duplicates(
        ["league", "season", "home_team", "away_team"],
        keep="last",
    ).sort_values("date", na_position="last")
    return current.reset_index(drop=True), training.reset_index(drop=True)


def _current_elo_models(
    current: pd.DataFrame,
    training: pd.DataFrame,
    config: LeagueConfig,
) -> tuple[EloResultModel, EloPoissonModel]:
    history = training[training["season"].astype(str) != config.season]
    if history.empty:
        ratings = fit_elo_ratings(current, home_advantage=config.home_advantage)
        return EloResultModel(ratings, config), EloPoissonModel(ratings, config)

    previous_code = max(history["season"].astype(str).unique())
    previous = history[history["season"].astype(str) == previous_code]
    previous_ratings = fit_elo_ratings(
        history,
        home_advantage=config.home_advantage,
    )
    current_teams = sorted(
        set(current["home_team"]).union(current["away_team"]),
        key=str.casefold,
    )
    rollover = season_rollover(previous, current, league=config)
    initial = rollover_ratings(
        previous_ratings,
        current_teams,
        promoted=rollover.promoted,
    )
    ratings = fit_elo_ratings(
        current,
        initial_ratings=initial,
        home_advantage=config.home_advantage,
    )
    return EloResultModel(ratings, config), EloPoissonModel(ratings, config)


def fit_league_models(
    current: pd.DataFrame,
    training: pd.DataFrame,
    config: LeagueConfig,
    *,
    names: Sequence[str] = MODEL_NAMES,
) -> dict[str, MatchModel]:
    models = fit_models(training, config, names=names)
    if "elo" in models or "elo_poisson" in models:
        elo, elo_poisson = _current_elo_models(current, training, config)
        if "elo" in models:
            models["elo"] = elo
        if "elo_poisson" in models:
            models["elo_poisson"] = elo_poisson
    return models


def evaluate_league_models(
    training: pd.DataFrame,
    config: LeagueConfig,
    *,
    names: Sequence[str] = MODEL_NAMES,
) -> pd.DataFrame:
    current_start = 2000 + int(config.season[:2])
    evaluation_start = f"{current_start - 1}-07-01"
    return compare_models(
        names,
        training,
        config,
        since=evaluation_start,
        min_train_matches=max(config.expected_matches * 2, 300),
        refit_every=max(config.expected_matches // 2, 100),
    )


def _select_fitted_model(
    models: dict[str, MatchModel],
    validation: pd.DataFrame,
    requested: str,
    *,
    use_ensemble: bool,
) -> str:
    if requested != "auto":
        if requested not in models:
            raise KeyError(f"Model {requested!r} was not fitted")
        return requested
    if validation.empty or validation["rps"].dropna().empty:
        return "dixon_coles" if "dixon_coles" in models else next(iter(models))
    if use_ensemble:
        weights = derive_ensemble_weights(validation, top_n=min(3, len(models)))
        selected = {name: models[name] for name in weights if name in models}
        if selected:
            models["ensemble"] = EnsembleModel(selected, weights)
            return "ensemble"
    champion = select_model(
        validation,
        baseline="elo",
        minimum_improvement=0.0,
    )
    return champion if champion in models else next(iter(models))


def build_forecast(
    league: str | LeagueConfig,
    *,
    data_root: str | Path = DEFAULT_DATA_ROOT,
    history_seasons: int = 5,
    model_name: str = "auto",
    use_ensemble: bool = False,
    run_validation: bool = True,
    n_simulations: int = 2_000,
    seed: int = 42,
) -> ForecastRun:
    config = get_league(league)
    current, training = load_training_matches(
        config,
        data_root=data_root,
        history_seasons=history_seasons,
    )
    models = fit_league_models(current, training, config)
    validation = (
        evaluate_league_models(training, config)
        if run_validation
        else pd.DataFrame(
            columns=[
                "model",
                "logloss",
                "brier",
                "rps",
                "calibration_error",
                "n_predictions",
                "calibration_bins",
            ]
        )
    )
    selected = _select_fitted_model(
        models,
        validation,
        model_name,
        use_ensemble=use_ensemble,
    )
    played, scheduled = split_played_scheduled(current)
    forecast = simulate_season(
        current,
        models[selected],
        results=played,
        league_config=config,
        n_simulations=int(n_simulations),
        seed=int(seed),
    )
    calibration = {
        str(row.model): {
            "calibration_error": row.calibration_error,
            "sample_size": row.n_predictions,
        }
        for row in validation.itertuples(index=False)
    }
    breakdowns = tuple(
        build_match_breakdowns(
            scheduled,
            models[selected],
            comparison_models=models,
            results=played,
            calibration=calibration,
            season_forecast=forecast,
        )
    )
    return ForecastRun(
        config=config,
        generated_at=datetime.now(timezone.utc).isoformat(),
        matches=current,
        training_matches=training,
        models=models,
        selected_model=selected,
        validation=validation,
        forecast=forecast,
        breakdowns=breakdowns,
    )


def build_breakdown_with_impact(
    run: ForecastRun,
    fixture: Any,
    *,
    n_simulations: int = 400,
    seed: int = 420,
) -> MatchBreakdown:
    played, _ = split_played_scheduled(run.matches)
    conditional = simulate_fixture_outcomes(
        run.matches,
        fixture,
        run.model,
        results=played,
        league_config=run.config,
        n_simulations=int(n_simulations),
        seed=int(seed),
    )
    calibration = {
        str(row.model): {
            "calibration_error": row.calibration_error,
            "sample_size": row.n_predictions,
        }
        for row in run.validation.itertuples(index=False)
    }
    return build_match_breakdown(
        fixture,
        run.model,
        comparison_models=run.models,
        results=played,
        calibration=calibration,
        season_forecast=run.forecast,
        outcome_forecasts=conditional,
    )


__all__ = [
    "ForecastRun",
    "build_breakdown_with_impact",
    "build_forecast",
    "evaluate_league_models",
    "fit_league_models",
    "load_training_matches",
]
