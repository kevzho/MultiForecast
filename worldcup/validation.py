"""Backtesting helpers for World Cup match models."""

from __future__ import annotations

import math
from typing import Callable

import numpy as np
import pandas as pd

from worldcup.models import MatchModel
from worldcup.team_names import normalize_intl_team

OUTCOMES = ("home", "draw", "away")


def backtest(
    model_factory: Callable[[], MatchModel],
    history: pd.DataFrame,
    since: str = "2018-01-01",
) -> dict:
    """Backtest pre-match W/D/L predictions against historical results."""

    model = model_factory()
    matches = history.copy()
    matches["date"] = pd.to_datetime(matches["date"])
    matches = matches[matches["date"] >= pd.Timestamp(since)].copy()
    matches["home_team"] = matches["home_team"].map(normalize_intl_team)
    matches["away_team"] = matches["away_team"].map(normalize_intl_team)
    matches = matches.dropna(
        subset=["home_team", "away_team", "home_score", "away_score"]
    )
    if "neutral" not in matches:
        matches["neutral"] = False

    loglosses: list[float] = []
    briers: list[float] = []
    rps_values: list[float] = []
    calibration_rows: list[dict] = []

    for row in matches.to_dict("records"):
        try:
            probs = _predict_wdl(model, row)
        except (KeyError, ValueError):
            continue
        actual = _actual_index(row["home_score"], row["away_score"])
        loglosses.append(-math.log(max(probs[actual], 1e-12)))
        briers.append(_brier(probs, actual))
        rps_values.append(_rps(probs, actual))
        for idx, outcome in enumerate(OUTCOMES):
            calibration_rows.append(
                {
                    "confidence": float(probs[idx]),
                    "hit": 1.0 if idx == actual else 0.0,
                    "outcome": outcome,
                }
            )

    if not loglosses:
        return {
            "logloss": math.nan,
            "brier": math.nan,
            "rps": math.nan,
            "calibration_bins": [],
        }

    return {
        "logloss": float(np.mean(loglosses)),
        "brier": float(np.mean(briers)),
        "rps": float(np.mean(rps_values)),
        "calibration_bins": _calibration_bins(calibration_rows),
    }


def compare_models(
    model_factories: dict[str, Callable[[], MatchModel]],
    history: pd.DataFrame,
    since: str = "2018-01-01",
) -> pd.DataFrame:
    rows = []
    for name, factory in model_factories.items():
        metrics = backtest(factory, history, since=since)
        rows.append(
            {
                "Model": name,
                "LogLoss": metrics["logloss"],
                "Brier": metrics["brier"],
                "RPS": metrics["rps"],
                "calibration_bins": metrics["calibration_bins"],
            }
        )
    return pd.DataFrame(rows).sort_values("RPS", ascending=True, na_position="last")


def _predict_wdl(model: MatchModel, row: dict) -> tuple[float, float, float]:
    if hasattr(model, "wdl_fast"):
        probs = model.wdl_fast(
            row["home_team"],
            row["away_team"],
            neutral=bool(row["neutral"]),
        )
    elif hasattr(model, "wdl"):
        probs = model.wdl(
            row["home_team"],
            row["away_team"],
            neutral=bool(row["neutral"]),
        )
    else:
        probs = model.predict(
            row["home_team"],
            row["away_team"],
            neutral=bool(row["neutral"]),
        ).wdl
    return _normalize_probs(probs)


def _normalize_probs(probs: tuple[float, float, float]) -> tuple[float, float, float]:
    arr = np.asarray(probs, dtype=float)
    arr = np.clip(arr, 1e-12, 1.0)
    arr = arr / arr.sum()
    return float(arr[0]), float(arr[1]), float(arr[2])


def _actual_index(home_score: float, away_score: float) -> int:
    if home_score > away_score:
        return 0
    if home_score < away_score:
        return 2
    return 1


def _brier(probs: tuple[float, float, float], actual: int) -> float:
    target = np.zeros(3)
    target[actual] = 1
    return float(np.sum((np.asarray(probs) - target) ** 2))


def _rps(probs: tuple[float, float, float], actual: int) -> float:
    target = np.zeros(3)
    target[actual] = 1
    pred_cdf = np.cumsum(np.asarray(probs))
    actual_cdf = np.cumsum(target)
    return float(np.sum((pred_cdf[:-1] - actual_cdf[:-1]) ** 2) / 2)


def _calibration_bins(rows: list[dict], n_bins: int = 10) -> list[dict]:
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    df["bin"] = pd.cut(
        df["confidence"],
        bins=np.linspace(0, 1, n_bins + 1),
        include_lowest=True,
    )
    grouped = df.groupby("bin", observed=True)
    bins = []
    for interval, group in grouped:
        bins.append(
            {
                "bin": str(interval),
                "mean_confidence": float(group["confidence"].mean()),
                "observed_frequency": float(group["hit"].mean()),
                "n": int(len(group)),
            }
        )
    return bins
