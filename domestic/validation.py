"""Walk-forward evaluation and domestic model selection."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from domestic.config import LeagueConfig, get_league
from domestic.models import (
    EnsembleModel,
    MODEL_NAMES,
    MatchModel,
    fit_models,
    make_model,
    model_name,
)


OUTCOMES = ("home", "draw", "away")
ModelFactory = Callable[[pd.DataFrame, LeagueConfig], MatchModel]


@dataclass(frozen=True)
class BacktestResult:
    model: str
    logloss: float
    brier: float
    rps: float
    n_predictions: int
    calibration_error: float
    calibration_bins: tuple[dict[str, object], ...]
    predictions: pd.DataFrame

    @property
    def metrics(self) -> dict[str, float | int]:
        return {
            "logloss": self.logloss,
            "brier": self.brier,
            "rps": self.rps,
            "n_predictions": self.n_predictions,
            "calibration_error": self.calibration_error,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            **self.metrics,
            "calibration_bins": list(self.calibration_bins),
            "predictions": self.predictions,
        }

    def __getitem__(self, key: str) -> object:
        return self.as_dict()[key]


def log_loss(probs: Sequence[float], actual: int) -> float:
    values = _probabilities(probs)
    return float(-math.log(max(float(values[actual]), 1e-12)))


def brier_score(probs: Sequence[float], actual: int) -> float:
    values = _probabilities(probs)
    target = np.zeros(3, dtype=float)
    target[actual] = 1.0
    return float(np.square(values - target).sum())


def ranked_probability_score(probs: Sequence[float], actual: int) -> float:
    values = _probabilities(probs)
    target = np.zeros(3, dtype=float)
    target[actual] = 1.0
    return float(np.square(np.cumsum(values)[:-1] - np.cumsum(target)[:-1]).sum() / 2)


def rolling_backtest(
    model: str | ModelFactory,
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    *,
    min_train_matches: int | None = None,
    refit_every: int = 20,
    since: str | pd.Timestamp | None = None,
    fit_kwargs: Mapping[str, object] | None = None,
    calibration_bins: int = 10,
) -> BacktestResult:
    """Evaluate predictions using only matches completed before each matchday."""

    league = get_league(config)
    frame = _prepare_results(matches)
    minimum = min_train_matches if min_train_matches is not None else max(50, league.team_count * 3)
    if minimum < 1:
        raise ValueError("min_train_matches must be positive")
    if refit_every < 1:
        raise ValueError("refit_every must be positive")
    start = pd.Timestamp(since) if since is not None else None
    label = model_name(model) if isinstance(model, str) else getattr(model, "__name__", "custom")
    kwargs = dict(fit_kwargs or {})
    predictions: list[dict[str, object]] = []
    fitted: MatchModel | None = None
    trained_count = -1

    for date, matchday in frame.groupby("date", sort=True):
        training = frame[frame["date"] < date]
        if len(training) < minimum:
            continue
        if start is not None and date < start:
            continue
        if fitted is None or len(training) - trained_count >= refit_every:
            fitted = _fit_model(model, training, league, kwargs)
            trained_count = len(training)
        for row in matchday.itertuples(index=False):
            dist = fitted.predict(row.home_team, row.away_team)
            probs = _probabilities(dist.wdl)
            actual = _actual_index(row.home_goals, row.away_goals)
            predictions.append(
                {
                    "date": date,
                    "home_team": row.home_team,
                    "away_team": row.away_team,
                    "home_goals": int(row.home_goals),
                    "away_goals": int(row.away_goals),
                    "actual": OUTCOMES[actual],
                    "p_home": float(probs[0]),
                    "p_draw": float(probs[1]),
                    "p_away": float(probs[2]),
                    "logloss": log_loss(probs, actual),
                    "brier": brier_score(probs, actual),
                    "rps": ranked_probability_score(probs, actual),
                    "scoreline_probability": float(
                        dist.grid[
                            min(int(row.home_goals), dist.grid.shape[0] - 1),
                            min(int(row.away_goals), dist.grid.shape[1] - 1),
                        ]
                    ),
                }
            )

    detail = pd.DataFrame(predictions)
    if detail.empty:
        return BacktestResult(
            model=label,
            logloss=math.nan,
            brier=math.nan,
            rps=math.nan,
            n_predictions=0,
            calibration_error=math.nan,
            calibration_bins=(),
            predictions=detail,
        )
    calibration = calibration_table(detail, n_bins=calibration_bins)
    calibration_records = tuple(calibration.to_dict("records"))
    calibration_error = float(
        np.average(
            np.abs(calibration["mean_probability"] - calibration["observed_frequency"]),
            weights=calibration["n"],
        )
    )
    return BacktestResult(
        model=label,
        logloss=float(detail["logloss"].mean()),
        brier=float(detail["brier"].mean()),
        rps=float(detail["rps"].mean()),
        n_predictions=int(len(detail)),
        calibration_error=calibration_error,
        calibration_bins=calibration_records,
        predictions=detail,
    )


def backtest(
    model: str | ModelFactory,
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    **kwargs: object,
) -> BacktestResult:
    return rolling_backtest(model, matches, config, **kwargs)


def calibration_table(predictions: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    if n_bins < 2:
        raise ValueError("n_bins must be at least two")
    if predictions.empty:
        return pd.DataFrame(
            columns=["outcome", "bin", "mean_probability", "observed_frequency", "n"]
        )
    rows: list[pd.DataFrame] = []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for outcome in OUTCOMES:
        probability = f"p_{outcome}"
        part = pd.DataFrame(
            {
                "outcome": outcome,
                "probability": pd.to_numeric(predictions[probability], errors="coerce"),
                "hit": predictions["actual"].eq(outcome).astype(float),
            }
        ).dropna()
        part["bin"] = pd.cut(
            part["probability"],
            bins=edges,
            include_lowest=True,
            duplicates="drop",
        )
        grouped = part.groupby("bin", observed=True)
        summary = grouped.agg(
            mean_probability=("probability", "mean"),
            observed_frequency=("hit", "mean"),
            n=("hit", "size"),
        ).reset_index()
        summary.insert(0, "outcome", outcome)
        summary["bin"] = summary["bin"].astype(str)
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def compare_models(
    models: Sequence[str] | Mapping[str, ModelFactory],
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    **kwargs: object,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    items = models.items() if isinstance(models, Mapping) else ((name, name) for name in models)
    for name, model in items:
        result = rolling_backtest(model, matches, config, **kwargs)
        rows.append(
            {
                "model": str(name),
                "logloss": result.logloss,
                "brier": result.brier,
                "rps": result.rps,
                "calibration_error": result.calibration_error,
                "n_predictions": result.n_predictions,
                "calibration_bins": list(result.calibration_bins),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["rps", "logloss"],
        ascending=True,
        na_position="last",
    ).reset_index(drop=True)


def select_model(
    comparison: pd.DataFrame | Mapping[str, BacktestResult],
    *,
    metric: str = "rps",
    baseline: str | None = None,
    minimum_improvement: float = 0.0,
) -> str:
    """Select a champion, optionally requiring improvement over a baseline."""

    if isinstance(comparison, Mapping):
        frame = pd.DataFrame(
            [{"model": name, **result.metrics} for name, result in comparison.items()]
        )
    else:
        frame = comparison.copy()
    if metric not in frame or "model" not in frame:
        raise ValueError(f"Comparison must include model and {metric}")
    candidates = frame.dropna(subset=[metric])
    if candidates.empty:
        raise ValueError("No models have finite backtest metrics")
    champion = candidates.sort_values([metric, "logloss"]).iloc[0]
    if baseline is not None and baseline in set(candidates["model"]):
        baseline_row = candidates[candidates["model"] == baseline].iloc[0]
        improvement = float(baseline_row[metric]) - float(champion[metric])
        if improvement < minimum_improvement:
            return baseline
    return str(champion["model"])


def derive_ensemble_weights(
    comparison: pd.DataFrame,
    *,
    metric: str = "rps",
    top_n: int = 3,
    temperature: float = 0.03,
) -> dict[str, float]:
    if top_n < 1 or temperature <= 0:
        raise ValueError("top_n and temperature must be positive")
    candidates = comparison.dropna(subset=[metric]).nsmallest(top_n, metric).copy()
    if candidates.empty:
        raise ValueError("No models have finite backtest metrics")
    losses = candidates[metric].to_numpy(dtype=float)
    weights = np.exp(-(losses - losses.min()) / temperature)
    weights /= weights.sum()
    return dict(zip(candidates["model"].astype(str), weights.astype(float)))


def fit_selected_model(
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    comparison: pd.DataFrame,
    *,
    metric: str = "rps",
    ensemble: bool = False,
    ensemble_top_n: int = 3,
    fit_kwargs: Mapping[str, object] | None = None,
) -> MatchModel:
    """Fit the selected champion or a performance-weighted ensemble on all data."""

    league = get_league(config)
    kwargs = dict(fit_kwargs or {})
    if not ensemble:
        return make_model(select_model(comparison, metric=metric), matches, league, **kwargs)
    weights = derive_ensemble_weights(
        comparison,
        metric=metric,
        top_n=ensemble_top_n,
    )
    fitted = fit_models(matches, league, names=tuple(weights), **kwargs)
    return EnsembleModel(fitted, weights)


def compare_default_models(
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    **kwargs: object,
) -> pd.DataFrame:
    return compare_models(MODEL_NAMES, matches, config, **kwargs)


def _fit_model(
    model: str | ModelFactory,
    training: pd.DataFrame,
    config: LeagueConfig,
    kwargs: Mapping[str, object],
) -> MatchModel:
    if isinstance(model, str):
        return make_model(model, training, config, **kwargs)
    try:
        return model(training, config, **kwargs)  # type: ignore[call-arg]
    except TypeError as first_error:
        try:
            return model(training, config)
        except TypeError:
            raise first_error


def _prepare_results(matches: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "home_team", "away_team", "home_goals", "away_goals"}
    missing = sorted(required - set(matches.columns))
    if missing:
        raise ValueError(f"Missing backtest columns: {missing}")
    frame = matches.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce")
    frame = frame.dropna(
        subset=["date", "home_team", "away_team", "home_goals", "away_goals"]
    )
    frame = frame.sort_values("date").reset_index(drop=True)
    return frame


def _probabilities(probs: Sequence[float]) -> np.ndarray:
    values = np.asarray(probs, dtype=float)
    if values.shape != (3,) or not np.isfinite(values).all():
        raise ValueError("W/D/L probabilities must contain three finite values")
    values = np.clip(values, 1e-12, 1.0)
    return values / values.sum()


def _actual_index(home_goals: float, away_goals: float) -> int:
    if home_goals > away_goals:
        return 0
    if home_goals < away_goals:
        return 2
    return 1

