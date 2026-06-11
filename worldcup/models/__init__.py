"""Selectable World Cup match-model registry."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from worldcup.data import load_elo
from worldcup.historical import load_history
from worldcup.model import EloModel, ScorelineDist
from worldcup.strengths import load_strengths
from worldcup.models.bradley_terry import BradleyTerryModel
from worldcup.models.dixon_coles import DixonColesModel
from worldcup.models.poisson import PoissonModel

STRENGTHS_PATH = Path(__file__).resolve().parents[2] / "data" / "wc" / "intl_strengths.csv"


class MatchModel(Protocol):
    def predict(self, home: str, away: str, *, neutral: bool = False) -> ScorelineDist:
        ...


def _elo_model() -> MatchModel:
    return EloModel(load_elo())


def _data_poisson_model() -> MatchModel:
    return PoissonModel(load_strengths(STRENGTHS_PATH))


def _dixon_coles_model() -> MatchModel:
    strengths = load_strengths(STRENGTHS_PATH)
    try:
        history = load_history()
    except FileNotFoundError:
        return DixonColesModel(strengths)
    return DixonColesModel.fit(strengths, history)


def _bradley_terry_model() -> MatchModel:
    strengths = load_strengths(STRENGTHS_PATH)
    elo = load_elo()
    try:
        history = load_history()
    except FileNotFoundError:
        return BradleyTerryModel.from_elo(strengths, elo)
    return BradleyTerryModel.fit(strengths, history, default_elo=elo)


AVAILABLE_MODELS: dict[str, Callable[[], MatchModel]] = {
    "Elo-Poisson": _elo_model,
    "Data Poisson": _data_poisson_model,
    "Dixon-Coles": _dixon_coles_model,
    "Bradley-Terry": _bradley_terry_model,
}


__all__ = ["AVAILABLE_MODELS", "MatchModel"]
