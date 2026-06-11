"""Dixon-Coles adjusted scoreline model."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from worldcup.model import MAX_GOALS, ScorelineDist, _poisson_pmf
from worldcup.strengths import StrengthTable
from worldcup.team_names import normalize_intl_team

DEFAULT_RHO = -0.13


class DixonColesModel:
    """Poisson score grid with the Dixon-Coles low-score correlation correction."""

    def __init__(self, strengths: StrengthTable, rho: float = DEFAULT_RHO) -> None:
        self.strengths = strengths
        self.rho = float(rho)

    @classmethod
    def fit(
        cls,
        strengths: StrengthTable,
        history: pd.DataFrame,
        default_rho: float = DEFAULT_RHO,
    ) -> "DixonColesModel":
        if history.empty:
            return cls(strengths, default_rho)

        matches = history.copy()
        matches["home_team"] = matches["home_team"].map(normalize_intl_team)
        matches["away_team"] = matches["away_team"].map(normalize_intl_team)
        matches = matches.dropna(
            subset=["home_team", "away_team", "home_score", "away_score"]
        )
        if "neutral" not in matches:
            matches["neutral"] = False
        if matches.empty:
            return cls(strengths, default_rho)

        def neg_loglike(rho: float) -> float:
            total = 0.0
            for row in matches.to_dict("records"):
                lam_h, lam_a = strengths.expected_goals(
                    row["home_team"],
                    row["away_team"],
                    neutral=bool(row["neutral"]),
                )
                tau = _tau(int(row["home_score"]), int(row["away_score"]), lam_h, lam_a, rho)
                if tau <= 0:
                    return math.inf
                total -= math.log(tau)
            return total

        result = minimize_scalar(neg_loglike, bounds=(-0.35, 0.35), method="bounded")
        if not result.success or not math.isfinite(float(result.fun)):
            # -0.13 is a common football Dixon-Coles starting value when direct
            # calibration is too thin or unstable for the available history.
            return cls(strengths, default_rho)
        return cls(strengths, float(result.x))

    def predict(self, home: str, away: str, *, neutral: bool = False) -> ScorelineDist:
        lam_h, lam_a = self.strengths.expected_goals(home, away, neutral=neutral)
        grid = np.outer(_poisson_pmf(lam_h), _poisson_pmf(lam_a))
        for hg in range(min(2, MAX_GOALS + 1)):
            for ag in range(min(2, MAX_GOALS + 1)):
                grid[hg, ag] *= _tau(hg, ag, lam_h, lam_a, self.rho)
        return ScorelineDist(grid / grid.sum())


def _tau(home_goals: int, away_goals: int, lam_h: float, lam_a: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1 - lam_h * lam_a * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + lam_h * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + lam_a * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0
