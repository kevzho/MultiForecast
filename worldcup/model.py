"""Match-outcome model for the standalone World Cup module."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from worldcup.data import load_elo
from worldcup.team_names import normalize_intl_team

MAX_GOALS = 10


@dataclass(frozen=True)
class ScorelineDist:
    """Probability grid over home and away goals from 0 through 10."""

    grid: np.ndarray

    def __post_init__(self) -> None:
        grid = np.asarray(self.grid, dtype=float)
        if grid.shape != (MAX_GOALS + 1, MAX_GOALS + 1):
            raise ValueError("ScorelineDist grid must have shape (11, 11)")
        total = grid.sum()
        if not np.isclose(total, 1.0):
            raise ValueError(f"ScorelineDist grid must sum to 1, got {total}")
        object.__setattr__(self, "grid", grid)

    @property
    def wdl(self) -> tuple[float, float, float]:
        p_home = float(np.tril(self.grid, k=-1).sum())
        p_draw = float(np.trace(self.grid))
        p_away = float(np.triu(self.grid, k=1).sum())
        return p_home, p_draw, p_away

    def sample(self, rng: np.random.Generator) -> tuple[int, int]:
        flat = self.grid.ravel()
        idx = rng.choice(flat.size, p=flat)
        home_goals, away_goals = np.unravel_index(idx, self.grid.shape)
        return int(home_goals), int(away_goals)


def make_rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(seed)


def seeded_rng(seed: int | None = None) -> np.random.Generator:
    return make_rng(seed)


def expected_score(
    elo_a: float,
    elo_b: float,
    home_adv: float = 0,
    scale: float = 400,
) -> float:
    rating_a_adj = elo_a + home_adv
    return 1 / (1 + math.pow(10, (elo_b - rating_a_adj) / scale))


def elo_to_match_probs(
    elo_h: float,
    elo_a: float,
    home_adv: float = 65,
    draw_rate: float = 0.26,
    neutral: bool = False,
) -> tuple[float, float, float]:
    if neutral:
        home_adv = 0
    exp_h = expected_score(elo_h, elo_a, home_adv=home_adv)
    exp_a = 1 - exp_h

    draw_prob = draw_rate
    win_prob_h = exp_h * (1 - draw_prob)
    win_prob_a = exp_a * (1 - draw_prob)

    return win_prob_h, draw_prob, win_prob_a


class EloModel:
    """Elo-anchored Poisson scoreline model.

    The model first converts Elo ratings into exact win/draw/loss probabilities using
    the same generalized Elo math as the Premier League model. It then builds an
    independent Poisson score grid whose expected total goals is approximately
    `avg_goals`, assigning the stronger side the larger scoring rate. Finally, it
    rescales the home-win, draw, and away-win regions so their masses exactly match
    the Elo-derived W/D/L probabilities.
    """

    def __init__(
        self,
        ratings: dict[str, float],
        home_adv: float = 65,
        draw_rate: float = 0.26,
        avg_goals: float = 2.6,
    ) -> None:
        self.ratings = {
            normalize_intl_team(team): float(rating) for team, rating in ratings.items()
        }
        self.home_adv = home_adv
        self.draw_rate = draw_rate
        self.avg_goals = avg_goals

    def predict(self, home: str, away: str, *, neutral: bool = False) -> ScorelineDist:
        home = normalize_intl_team(home)
        away = normalize_intl_team(away)
        elo_h = self.ratings[home]
        elo_a = self.ratings[away]

        p_home, p_draw, p_away = elo_to_match_probs(
            elo_h,
            elo_a,
            self.home_adv,
            self.draw_rate,
            neutral=neutral,
        )
        lam_h, lam_a = self._poisson_rates(elo_h, elo_a, neutral=neutral)
        grid = np.outer(_poisson_pmf(lam_h), _poisson_pmf(lam_a))
        grid = grid / grid.sum()
        grid = _rescale_wdl(grid, p_home, p_draw, p_away)
        return ScorelineDist(grid)

    def _poisson_rates(
        self,
        elo_h: float,
        elo_a: float,
        *,
        neutral: bool = False,
    ) -> tuple[float, float]:
        adjusted_home = elo_h + (0 if neutral else self.home_adv)
        ratio = math.pow(10, (adjusted_home - elo_a) / 800)
        lam_h = self.avg_goals * ratio / (1 + ratio)
        lam_a = self.avg_goals - lam_h
        return max(lam_h, 0.05), max(lam_a, 0.05)


def sample_scoreline(
    dist: ScorelineDist,
    rng: np.random.Generator,
) -> tuple[int, int]:
    return dist.sample(rng)


def _poisson_pmf(lam: float) -> np.ndarray:
    goals = np.arange(MAX_GOALS + 1)
    return np.array(
        [math.exp(-lam) * math.pow(lam, int(k)) / math.factorial(int(k)) for k in goals],
        dtype=float,
    )


def _rescale_wdl(
    grid: np.ndarray,
    p_home: float,
    p_draw: float,
    p_away: float,
) -> np.ndarray:
    home_mask = np.tril(np.ones_like(grid, dtype=bool), k=-1)
    draw_mask = np.eye(grid.shape[0], dtype=bool)
    away_mask = np.triu(np.ones_like(grid, dtype=bool), k=1)

    scaled = grid.copy()
    for mask, target in (
        (home_mask, p_home),
        (draw_mask, p_draw),
        (away_mask, p_away),
    ):
        current = scaled[mask].sum()
        if current <= 0:
            raise ValueError("Cannot rescale a zero-mass W/D/L region")
        scaled[mask] *= target / current

    return scaled / scaled.sum()


if __name__ == "__main__":
    model = EloModel(load_elo())
    dist = model.predict("Spain", "Cape Verde")
    rng = make_rng(2026)
    print("Spain vs Cape Verde W/D/L:", dist.wdl)
    print("Sample scoreline:", sample_scoreline(dist, rng))
