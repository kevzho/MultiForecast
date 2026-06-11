"""Independent Poisson model driven by empirical team strengths."""

from __future__ import annotations

import numpy as np

from worldcup.model import ScorelineDist, _poisson_pmf
from worldcup.models.skellam import skellam_wdl
from worldcup.strengths import StrengthTable


class PoissonModel:
    def __init__(self, strengths: StrengthTable) -> None:
        self.strengths = strengths

    def expected_goals(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
    ) -> tuple[float, float]:
        return self.strengths.expected_goals(home, away, neutral=neutral)

    def predict(self, home: str, away: str, *, neutral: bool = False) -> ScorelineDist:
        lam_h, lam_a = self.expected_goals(home, away, neutral=neutral)
        grid = np.outer(_poisson_pmf(lam_h), _poisson_pmf(lam_a))
        return ScorelineDist(grid / grid.sum())

    def wdl_fast(self, home: str, away: str, *, neutral: bool = False) -> tuple[float, float, float]:
        lam_h, lam_a = self.expected_goals(home, away, neutral=neutral)
        return skellam_wdl(lam_h, lam_a)
