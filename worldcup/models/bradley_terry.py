"""Bradley-Terry/Davidson W/D/L comparison model."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from worldcup.model import ScorelineDist, _poisson_pmf, _rescale_wdl
from worldcup.strengths import StrengthTable
from worldcup.team_names import normalize_intl_team


@dataclass(frozen=True)
class DavidsonParams:
    strengths: dict[str, float]
    draw: float
    home_adv: float = 0.0


class BradleyTerryModel:
    """Comparison model: Davidson W/D/L probabilities shape a Poisson goal grid."""

    def __init__(self, goal_strengths: StrengthTable, params: DavidsonParams) -> None:
        self.goal_strengths = goal_strengths
        self.params = params

    @classmethod
    def from_elo(
        cls,
        goal_strengths: StrengthTable,
        elo: dict[str, float],
        draw: float = 0.7,
    ) -> "BradleyTerryModel":
        normalized = {normalize_intl_team(team): float(rating) for team, rating in elo.items()}
        if not normalized:
            teams = sorted(set(goal_strengths.attack).union(goal_strengths.defense))
            strengths = {team: 0.0 for team in teams}
            return cls(goal_strengths, DavidsonParams(strengths, draw))
        mean_elo = float(np.mean(list(normalized.values())))
        scale = math.log(10) / 400
        strengths = {team: (rating - mean_elo) * scale for team, rating in normalized.items()}
        return cls(goal_strengths, DavidsonParams(strengths, draw))

    @classmethod
    def fit(
        cls,
        goal_strengths: StrengthTable,
        history: pd.DataFrame,
        default_elo: dict[str, float] | None = None,
    ) -> "BradleyTerryModel":
        matches = history.copy()
        matches["home_team"] = matches["home_team"].map(normalize_intl_team)
        matches["away_team"] = matches["away_team"].map(normalize_intl_team)
        matches = matches.dropna(
            subset=["home_team", "away_team", "home_score", "away_score"]
        )
        if matches.empty:
            return cls.from_elo(goal_strengths, default_elo or {})
        if "neutral" not in matches:
            matches["neutral"] = False

        teams = sorted(set(matches["home_team"]).union(matches["away_team"]))
        team_index = {team: idx for idx, team in enumerate(teams[:-1])}

        def unpack(values: np.ndarray) -> DavidsonParams:
            strengths = {team: 0.0 for team in teams}
            for team, idx in team_index.items():
                strengths[team] = float(values[idx])
            mean_strength = float(np.mean(list(strengths.values())))
            strengths = {team: value - mean_strength for team, value in strengths.items()}
            draw = math.exp(float(values[len(team_index)]))
            home_adv = float(values[len(team_index) + 1])
            return DavidsonParams(strengths, draw, home_adv)

        def neg_loglike(values: np.ndarray) -> float:
            params = unpack(values)
            total = 0.0
            for row in matches.to_dict("records"):
                p_home, p_draw, p_away = _davidson_wdl(
                    params,
                    row["home_team"],
                    row["away_team"],
                    neutral=bool(row["neutral"]),
                )
                if row["home_score"] > row["away_score"]:
                    prob = p_home
                elif row["home_score"] < row["away_score"]:
                    prob = p_away
                else:
                    prob = p_draw
                total -= math.log(max(prob, 1e-12))
            return total

        initial = np.zeros(len(team_index) + 2)
        initial[len(team_index)] = math.log(0.7)
        from scipy.optimize import minimize

        result = minimize(neg_loglike, initial, method="BFGS")
        if not result.success:
            return cls.from_elo(goal_strengths, default_elo or {})
        return cls(goal_strengths, unpack(result.x))

    def wdl(self, home: str, away: str, *, neutral: bool = False) -> tuple[float, float, float]:
        home = normalize_intl_team(home)
        away = normalize_intl_team(away)
        return _davidson_wdl(self.params, home, away, neutral=neutral)

    def predict(self, home: str, away: str, *, neutral: bool = False) -> ScorelineDist:
        lam_h, lam_a = self.goal_strengths.expected_goals(home, away, neutral=neutral)
        grid = np.outer(_poisson_pmf(lam_h), _poisson_pmf(lam_a))
        grid = grid / grid.sum()
        p_home, p_draw, p_away = self.wdl(home, away, neutral=neutral)
        return ScorelineDist(_rescale_wdl(grid, p_home, p_draw, p_away))


def _davidson_wdl(
    params: DavidsonParams,
    home: str,
    away: str,
    *,
    neutral: bool = False,
) -> tuple[float, float, float]:
    home_strength = params.strengths.get(home, 0.0) + (0.0 if neutral else params.home_adv)
    away_strength = params.strengths.get(away, 0.0)
    alpha_h = math.exp(home_strength)
    alpha_a = math.exp(away_strength)
    draw_term = params.draw * math.sqrt(alpha_h * alpha_a)
    denom = alpha_h + alpha_a + draw_term
    return alpha_h / denom, draw_term / denom, alpha_a / denom
