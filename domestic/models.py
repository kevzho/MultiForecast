"""Shared scoreline models for domestic leagues."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Protocol, Sequence, runtime_checkable

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln
from scipy.stats import skellam

from domestic.config import LeagueConfig, get_league


MAX_GOALS = 10
MODEL_NAMES = (
    "elo",
    "elo_poisson",
    "poisson",
    "dixon_coles",
    "bradley_terry",
)


@dataclass(frozen=True)
class ScorelineDist:
    """Probability grid for home and away goals from zero through ten."""

    grid: np.ndarray

    def __post_init__(self) -> None:
        grid = np.asarray(self.grid, dtype=float)
        expected_shape = (MAX_GOALS + 1, MAX_GOALS + 1)
        if grid.shape != expected_shape:
            raise ValueError(f"ScorelineDist grid must have shape {expected_shape}")
        if not np.isfinite(grid).all() or (grid < 0).any():
            raise ValueError("ScorelineDist probabilities must be finite and non-negative")
        total = float(grid.sum())
        if not np.isclose(total, 1.0, atol=1e-8):
            raise ValueError(f"ScorelineDist grid must sum to 1, got {total}")
        frozen = grid.copy()
        frozen.setflags(write=False)
        object.__setattr__(self, "grid", frozen)

    @property
    def wdl(self) -> tuple[float, float, float]:
        return (
            float(np.tril(self.grid, k=-1).sum()),
            float(np.trace(self.grid)),
            float(np.triu(self.grid, k=1).sum()),
        )

    @property
    def expected_goals(self) -> tuple[float, float]:
        goals = np.arange(self.grid.shape[0], dtype=float)
        return (
            float((self.grid * goals[:, None]).sum()),
            float((self.grid * goals[None, :]).sum()),
        )

    @property
    def both_teams_to_score(self) -> float:
        return float(self.grid[1:, 1:].sum())

    @property
    def home_clean_sheet(self) -> float:
        return float(self.grid[:, 0].sum())

    @property
    def away_clean_sheet(self) -> float:
        return float(self.grid[0, :].sum())

    def total_over(self, line: float = 2.5) -> float:
        home, away = np.indices(self.grid.shape)
        return float(self.grid[(home + away) > line].sum())

    def top_scorelines(self, n: int = 5) -> tuple[tuple[int, int, float], ...]:
        if n < 1:
            return ()
        order = np.argsort(self.grid.ravel())[::-1][:n]
        return tuple(
            (
                int(np.unravel_index(index, self.grid.shape)[0]),
                int(np.unravel_index(index, self.grid.shape)[1]),
                float(self.grid.ravel()[index]),
            )
            for index in order
        )

    def sample(self, rng: np.random.Generator) -> tuple[int, int]:
        index = int(rng.choice(self.grid.size, p=self.grid.ravel()))
        home, away = np.unravel_index(index, self.grid.shape)
        return int(home), int(away)


@runtime_checkable
class MatchModel(Protocol):
    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist: ...


def make_rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(seed)


def expected_score(
    rating_home: float,
    rating_away: float,
    *,
    home_advantage: float = 0.0,
    scale: float = 400.0,
) -> float:
    exponent = (rating_away - rating_home - home_advantage) / scale
    return float(1.0 / (1.0 + math.pow(10.0, exponent)))


def elo_wdl(
    rating_home: float,
    rating_away: float,
    *,
    home_advantage: float,
    draw_rate: float,
    neutral: bool = False,
) -> tuple[float, float, float]:
    home_edge = 0.0 if neutral else home_advantage
    decisive_home = expected_score(
        rating_home,
        rating_away,
        home_advantage=home_edge,
    )
    draw = float(np.clip(draw_rate, 0.01, 0.80))
    return decisive_home * (1 - draw), draw, (1 - decisive_home) * (1 - draw)


def fit_elo_ratings(
    matches: pd.DataFrame,
    *,
    initial_ratings: Mapping[str, float] | None = None,
    base_rating: float = 1500.0,
    k_factor: float = 20.0,
    home_advantage: float = 70.0,
    season_regression: float = 0.15,
    promotion_gap: float = 20.0,
) -> dict[str, float]:
    frame = _played_matches(matches)
    teams = _all_teams(matches)
    initial = {team: float(value) for team, value in (initial_ratings or {}).items()}
    ratings = {team: float(base_rating) for team in teams}
    ratings.update(initial)
    ordered = frame.sort_values("date", na_position="last")
    season_teams = (
        {
            str(season): set(part["home_team"]).union(part["away_team"])
            for season, part in ordered.groupby("season", sort=False)
        }
        if "season" in ordered
        else {}
    )
    previous_season: str | None = None
    for row in ordered.itertuples(index=False):
        current_season = str(row.season) if hasattr(row, "season") else None
        if (
            current_season is not None
            and previous_season is not None
            and current_season != previous_season
        ):
            previous_teams = season_teams.get(previous_season, set())
            current_teams = season_teams.get(current_season, set())
            promoted = sorted(current_teams - previous_teams)
            previous_active_ratings = {
                team: ratings.get(team, base_rating) for team in previous_teams
            }
            ratings = rollover_ratings(
                previous_active_ratings,
                sorted(current_teams),
                promoted=promoted,
                promoted_seeds=initial,
                base_rating=base_rating,
                regression=season_regression,
                promotion_gap=promotion_gap,
            )
        previous_season = current_season
        ratings.setdefault(row.home_team, float(base_rating))
        ratings.setdefault(row.away_team, float(base_rating))
        home_rating = ratings[row.home_team]
        away_rating = ratings[row.away_team]
        expected_home = expected_score(
            home_rating,
            away_rating,
            home_advantage=home_advantage,
        )
        if row.home_goals > row.away_goals:
            actual_home = 1.0
        elif row.home_goals < row.away_goals:
            actual_home = 0.0
        else:
            actual_home = 0.5
        change = k_factor * (actual_home - expected_home)
        ratings[row.home_team] = home_rating + change
        ratings[row.away_team] = away_rating - change
    return ratings


def rollover_ratings(
    previous_ratings: Mapping[str, float],
    current_teams: Sequence[str],
    *,
    promoted: Sequence[str] = (),
    promoted_seeds: Mapping[str, float] | None = None,
    base_rating: float = 1500.0,
    regression: float = 0.20,
    promotion_gap: float = 20.0,
) -> dict[str, float]:
    """Regress returning ratings and seed newly promoted teams below the floor."""

    if not 0 <= regression <= 1:
        raise ValueError("regression must be between zero and one")
    current = tuple(dict.fromkeys(str(team) for team in current_teams))
    returning = [team for team in current if team in previous_ratings]
    rolled = {
        team: base_rating
        + (float(previous_ratings[team]) - base_rating) * (1.0 - regression)
        for team in returning
    }
    floor = min(rolled.values(), default=base_rating) - promotion_gap
    explicit = {team: float(value) for team, value in (promoted_seeds or {}).items()}
    promoted_order = tuple(dict.fromkeys(str(team) for team in promoted))
    for index, team in enumerate(promoted_order):
        rolled[team] = explicit.get(team, floor - index * promotion_gap / 3)
    for team in current:
        rolled.setdefault(team, explicit.get(team, floor))
    return rolled


def skellam_wdl(home_rate: float, away_rate: float) -> tuple[float, float, float]:
    """Return exact W/D/L probabilities for two independent Poisson rates."""

    if home_rate <= 0 or away_rate <= 0:
        raise ValueError("Poisson rates must be positive")
    away = float(skellam.cdf(-1, home_rate, away_rate))
    draw = float(skellam.pmf(0, home_rate, away_rate))
    home = float(1.0 - skellam.cdf(0, home_rate, away_rate))
    total = home + draw + away
    return home / total, draw / total, away / total


class EloResultModel:
    """Result-only Elo baseline wrapped in a scoreline distribution."""

    def __init__(
        self,
        ratings: Mapping[str, float],
        config: str | LeagueConfig,
        *,
        base_rating: float = 1500.0,
    ) -> None:
        self.config = get_league(config)
        self.ratings = {str(team): float(value) for team, value in ratings.items()}
        self.base_rating = float(base_rating)

    @classmethod
    def fit(
        cls,
        matches: pd.DataFrame,
        config: str | LeagueConfig,
        **kwargs: object,
    ) -> "EloResultModel":
        league = get_league(config)
        initial = kwargs.get("initial_ratings")
        ratings = fit_elo_ratings(
            matches,
            initial_ratings=initial if isinstance(initial, Mapping) else None,
            base_rating=float(kwargs.get("base_rating", 1500.0)),
            k_factor=float(kwargs.get("k_factor", 20.0)),
            home_advantage=league.home_advantage,
            season_regression=float(kwargs.get("season_regression", 0.15)),
            promotion_gap=float(kwargs.get("promotion_gap", 20.0)),
        )
        return cls(ratings, league, base_rating=float(kwargs.get("base_rating", 1500.0)))

    def wdl(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> tuple[float, float, float]:
        neutral = _context_neutral(neutral, context)
        return elo_wdl(
            self.ratings.get(home, self.base_rating),
            self.ratings.get(away, self.base_rating),
            home_advantage=self.config.home_advantage,
            draw_rate=self.config.draw_rate,
            neutral=neutral,
        )

    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist:
        neutral = _context_neutral(neutral, context)
        p_home, p_draw, p_away = self.wdl(home, away, neutral=neutral)
        home_share = 0.5 if neutral else 0.54
        home_rate = self.config.avg_goals * home_share
        away_rate = self.config.avg_goals - home_rate
        grid = _independent_poisson_grid(home_rate, away_rate)
        return ScorelineDist(_rescale_wdl(grid, p_home, p_draw, p_away))


class EloPoissonModel(EloResultModel):
    """Elo W/D/L probabilities with strength-dependent Poisson score rates."""

    def expected_goals(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> tuple[float, float]:
        neutral = _context_neutral(neutral, context)
        home_rating = self.ratings.get(home, self.base_rating)
        away_rating = self.ratings.get(away, self.base_rating)
        adjusted_home = home_rating + (0.0 if neutral else self.config.home_advantage)
        ratio = math.pow(10.0, (adjusted_home - away_rating) / 800.0)
        home_rate = self.config.avg_goals * ratio / (1.0 + ratio)
        away_rate = self.config.avg_goals - home_rate
        return max(home_rate, 0.05), max(away_rate, 0.05)

    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist:
        neutral = _context_neutral(neutral, context)
        rates = self.expected_goals(home, away, neutral=neutral)
        grid = _independent_poisson_grid(*rates)
        return ScorelineDist(_rescale_wdl(grid, *self.wdl(home, away, neutral=neutral)))


@dataclass(frozen=True, slots=True)
class StrengthTable:
    attack: dict[str, float]
    defense: dict[str, float]
    base_rate: float
    home_advantage: float

    def expected_goals(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
    ) -> tuple[float, float]:
        home_edge = 0.0 if neutral else self.home_advantage
        home_rate = math.exp(
            self.base_rate
            + self.attack.get(home, 0.0)
            + self.defense.get(away, 0.0)
            + home_edge
        )
        away_rate = math.exp(
            self.base_rate
            + self.attack.get(away, 0.0)
            + self.defense.get(home, 0.0)
        )
        return float(np.clip(home_rate, 0.03, 8.0)), float(np.clip(away_rate, 0.03, 8.0))


def fit_strengths(
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    *,
    half_life_days: float = 365.0,
    l2: float = 0.08,
) -> StrengthTable:
    """Fit recency-weighted attack and defense rates by maximum likelihood."""

    league = get_league(config)
    frame = _played_matches(matches)
    teams = sorted(_all_teams(matches))
    default = StrengthTable(
        attack={team: 0.0 for team in teams},
        defense={team: 0.0 for team in teams},
        base_rate=math.log(max(league.avg_goals / 2.0, 0.05)),
        home_advantage=league.home_advantage * math.log(10.0) / 800.0,
    )
    if frame.empty or len(teams) < 2:
        return default

    index = {team: idx for idx, team in enumerate(teams)}
    home_idx = frame["home_team"].map(index).to_numpy(dtype=int)
    away_idx = frame["away_team"].map(index).to_numpy(dtype=int)
    home_goals = frame["home_goals"].to_numpy(dtype=float)
    away_goals = frame["away_goals"].to_numpy(dtype=float)
    weights = _recency_weights(frame["date"], half_life_days)
    n_teams = len(teams)

    overall = max(float((home_goals.sum() + away_goals.sum()) / (2 * len(frame))), 0.05)
    home_ratio = max(float((home_goals.mean() + 0.05) / (away_goals.mean() + 0.05)), 0.1)
    initial = np.zeros(2 * n_teams + 2, dtype=float)
    initial[-2] = math.log(overall)
    initial[-1] = math.log(home_ratio)

    def objective(values: np.ndarray) -> float:
        attack = values[:n_teams]
        defense = values[n_teams : 2 * n_teams]
        base = values[-2]
        home_edge = values[-1]
        log_home = np.clip(
            base + home_edge + attack[home_idx] + defense[away_idx], -5.0, 3.0
        )
        log_away = np.clip(base + attack[away_idx] + defense[home_idx], -5.0, 3.0)
        likelihood = weights * (
            np.exp(log_home)
            - home_goals * log_home
            + gammaln(home_goals + 1)
            + np.exp(log_away)
            - away_goals * log_away
            + gammaln(away_goals + 1)
        )
        penalty = l2 * (np.square(attack).sum() + np.square(defense).sum())
        return float(likelihood.sum() + penalty)

    result = minimize(objective, initial, method="L-BFGS-B")
    if not result.success or not np.isfinite(result.fun):
        return default
    values = np.asarray(result.x, dtype=float)
    attack_values = values[:n_teams]
    defense_values = values[n_teams : 2 * n_teams]
    attack_mean = float(attack_values.mean())
    defense_mean = float(defense_values.mean())
    attack_values -= attack_mean
    defense_values -= defense_mean
    base_rate = float(values[-2] + attack_mean + defense_mean)
    return StrengthTable(
        attack=dict(zip(teams, attack_values.astype(float))),
        defense=dict(zip(teams, defense_values.astype(float))),
        base_rate=base_rate,
        home_advantage=float(values[-1]),
    )


class PoissonModel:
    def __init__(self, strengths: StrengthTable) -> None:
        self.strengths = strengths

    @classmethod
    def fit(
        cls,
        matches: pd.DataFrame,
        config: str | LeagueConfig,
        **kwargs: object,
    ) -> "PoissonModel":
        provided = kwargs.get("strengths")
        if isinstance(provided, StrengthTable):
            return cls(provided)
        return cls(
            fit_strengths(
                matches,
                config,
                half_life_days=float(kwargs.get("half_life_days", 365.0)),
                l2=float(kwargs.get("l2", 0.08)),
            )
        )

    def expected_goals(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> tuple[float, float]:
        return self.strengths.expected_goals(
            home,
            away,
            neutral=_context_neutral(neutral, context),
        )

    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist:
        rates = self.expected_goals(home, away, neutral=neutral, context=context)
        return ScorelineDist(_independent_poisson_grid(*rates))

    def wdl_fast(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> tuple[float, float, float]:
        rates = self.expected_goals(home, away, neutral=neutral, context=context)
        return skellam_wdl(*rates)


class DixonColesModel(PoissonModel):
    def __init__(self, strengths: StrengthTable, rho: float = -0.08) -> None:
        super().__init__(strengths)
        self.rho = float(rho)

    @classmethod
    def fit(
        cls,
        matches: pd.DataFrame,
        config: str | LeagueConfig,
        **kwargs: object,
    ) -> "DixonColesModel":
        strengths = kwargs.get("strengths")
        if not isinstance(strengths, StrengthTable):
            strengths = fit_strengths(
                matches,
                config,
                half_life_days=float(kwargs.get("half_life_days", 365.0)),
                l2=float(kwargs.get("l2", 0.08)),
            )
        frame = _played_matches(matches)
        default_rho = float(kwargs.get("default_rho", -0.08))
        if frame.empty:
            return cls(strengths, default_rho)

        def objective(rho: float) -> float:
            total = 0.0
            for row in frame.itertuples(index=False):
                home_rate, away_rate = strengths.expected_goals(row.home_team, row.away_team)
                adjustment = _dixon_coles_tau(
                    int(row.home_goals),
                    int(row.away_goals),
                    home_rate,
                    away_rate,
                    rho,
                )
                if adjustment <= 0:
                    return math.inf
                total -= math.log(adjustment)
            return total

        result = minimize_scalar(objective, bounds=(-0.30, 0.20), method="bounded")
        rho = float(result.x) if result.success and math.isfinite(result.fun) else default_rho
        return cls(strengths, rho)

    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist:
        home_rate, away_rate = self.expected_goals(
            home,
            away,
            neutral=neutral,
            context=context,
        )
        grid = _independent_poisson_grid(home_rate, away_rate)
        for home_goals in (0, 1):
            for away_goals in (0, 1):
                grid[home_goals, away_goals] *= max(
                    _dixon_coles_tau(
                        home_goals,
                        away_goals,
                        home_rate,
                        away_rate,
                        self.rho,
                    ),
                    1e-12,
                )
        return ScorelineDist(grid / grid.sum())


@dataclass(frozen=True, slots=True)
class DavidsonParams:
    strengths: dict[str, float]
    draw: float
    home_advantage: float


class BradleyTerryModel(PoissonModel):
    def __init__(self, goal_strengths: StrengthTable, params: DavidsonParams) -> None:
        super().__init__(goal_strengths)
        self.params = params

    @classmethod
    def fit(
        cls,
        matches: pd.DataFrame,
        config: str | LeagueConfig,
        **kwargs: object,
    ) -> "BradleyTerryModel":
        league = get_league(config)
        goal_strengths = kwargs.get("strengths")
        if not isinstance(goal_strengths, StrengthTable):
            goal_strengths = fit_strengths(matches, league)
        frame = _played_matches(matches)
        teams = sorted(_all_teams(matches))
        if frame.empty or len(teams) < 2:
            return cls(
                goal_strengths,
                DavidsonParams(
                    {team: 0.0 for team in teams},
                    draw=0.7,
                    home_advantage=league.home_advantage * math.log(10.0) / 400.0,
                ),
            )
        index = {team: idx for idx, team in enumerate(teams)}
        home_idx = frame["home_team"].map(index).to_numpy(dtype=int)
        away_idx = frame["away_team"].map(index).to_numpy(dtype=int)
        outcomes = np.select(
            [
                frame["home_goals"].to_numpy() > frame["away_goals"].to_numpy(),
                frame["home_goals"].to_numpy() < frame["away_goals"].to_numpy(),
            ],
            [0, 2],
            default=1,
        )
        weights = _recency_weights(frame["date"], float(kwargs.get("half_life_days", 365.0)))
        n_teams = len(teams)
        initial = np.zeros(n_teams + 2)
        initial[-2] = math.log(0.7)
        initial[-1] = league.home_advantage * math.log(10.0) / 400.0
        l2 = float(kwargs.get("l2", 0.08))

        def objective(values: np.ndarray) -> float:
            strength = values[:n_teams]
            home_alpha = np.exp(np.clip(strength[home_idx] + values[-1], -8, 8))
            away_alpha = np.exp(np.clip(strength[away_idx], -8, 8))
            draw_term = math.exp(float(np.clip(values[-2], -5, 3))) * np.sqrt(
                home_alpha * away_alpha
            )
            denominator = home_alpha + away_alpha + draw_term
            probabilities = np.column_stack(
                (home_alpha / denominator, draw_term / denominator, away_alpha / denominator)
            )
            selected = probabilities[np.arange(len(frame)), outcomes]
            return float(
                -(weights * np.log(np.clip(selected, 1e-12, 1.0))).sum()
                + l2 * np.square(strength).sum()
            )

        result = minimize(objective, initial, method="L-BFGS-B")
        values = np.asarray(result.x if result.success else initial, dtype=float)
        strengths = values[:n_teams] - values[:n_teams].mean()
        params = DavidsonParams(
            dict(zip(teams, strengths.astype(float))),
            draw=math.exp(float(values[-2])),
            home_advantage=float(values[-1]),
        )
        return cls(goal_strengths, params)

    def wdl(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> tuple[float, float, float]:
        neutral = _context_neutral(neutral, context)
        home_strength = self.params.strengths.get(home, 0.0)
        if not neutral:
            home_strength += self.params.home_advantage
        away_strength = self.params.strengths.get(away, 0.0)
        home_alpha = math.exp(float(np.clip(home_strength, -8, 8)))
        away_alpha = math.exp(float(np.clip(away_strength, -8, 8)))
        draw_term = self.params.draw * math.sqrt(home_alpha * away_alpha)
        denominator = home_alpha + away_alpha + draw_term
        return (
            home_alpha / denominator,
            draw_term / denominator,
            away_alpha / denominator,
        )

    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist:
        neutral = _context_neutral(neutral, context)
        grid = _independent_poisson_grid(
            *self.expected_goals(home, away, neutral=neutral)
        )
        return ScorelineDist(_rescale_wdl(grid, *self.wdl(home, away, neutral=neutral)))


class EnsembleModel:
    def __init__(
        self,
        models: Mapping[str, MatchModel] | Sequence[MatchModel],
        weights: Mapping[str, float] | Sequence[float] | None = None,
    ) -> None:
        if isinstance(models, Mapping):
            self.names = tuple(models)
            self.models = tuple(models.values())
        else:
            self.models = tuple(models)
            self.names = tuple(f"model_{index}" for index in range(len(self.models)))
        if not self.models:
            raise ValueError("An ensemble needs at least one model")
        if isinstance(weights, Mapping):
            values = np.array([weights.get(name, 0.0) for name in self.names], dtype=float)
        elif weights is None:
            values = np.ones(len(self.models), dtype=float)
        else:
            values = np.asarray(weights, dtype=float)
        if values.shape != (len(self.models),) or (values < 0).any() or values.sum() <= 0:
            raise ValueError("Ensemble weights must be non-negative and match the models")
        self.weights = values / values.sum()

    def predict(
        self,
        home: str,
        away: str,
        *,
        neutral: bool = False,
        context: Mapping[str, object] | None = None,
    ) -> ScorelineDist:
        grid = sum(
            weight * model.predict(home, away, neutral=neutral, context=context).grid
            for weight, model in zip(self.weights, self.models)
        )
        return ScorelineDist(np.asarray(grid, dtype=float) / np.asarray(grid).sum())


MODEL_REGISTRY = {
    "elo": EloResultModel,
    "elo_poisson": EloPoissonModel,
    "poisson": PoissonModel,
    "dixon_coles": DixonColesModel,
    "bradley_terry": BradleyTerryModel,
}
AVAILABLE_MODELS = MODEL_REGISTRY
EloModel = EloResultModel
AttackDefensePoissonModel = PoissonModel

_MODEL_ALIASES = {
    "elo_result": "elo",
    "elo-poisson": "elo_poisson",
    "attack_defense_poisson": "poisson",
    "data_poisson": "poisson",
    "dixon-coles": "dixon_coles",
    "bradley-terry": "bradley_terry",
    "davidson": "bradley_terry",
}


def model_name(value: str) -> str:
    key = value.strip().lower().replace(" ", "_")
    key = _MODEL_ALIASES.get(key, key)
    if key not in MODEL_REGISTRY:
        raise KeyError(f"Unknown model {value!r}. Available models: {', '.join(MODEL_NAMES)}")
    return key


def make_model(
    name: str,
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    **kwargs: object,
) -> MatchModel:
    key = model_name(name)
    return MODEL_REGISTRY[key].fit(matches, get_league(config), **kwargs)


def fit_models(
    matches: pd.DataFrame,
    config: str | LeagueConfig,
    names: Sequence[str] | None = None,
    *,
    ensemble_weights: Mapping[str, float] | None = None,
    **kwargs: object,
) -> dict[str, MatchModel]:
    """Fit requested models while sharing the expensive strength estimates."""

    league = get_league(config)
    requested = tuple(model_name(name) for name in (names or MODEL_NAMES))
    fitted: dict[str, MatchModel] = {}
    provided_strengths = kwargs.get("strengths")
    strengths = provided_strengths if isinstance(provided_strengths, StrengthTable) else None
    ratings: dict[str, float] | None = None
    fit_kwargs = {key: value for key, value in kwargs.items() if key != "strengths"}
    if any(name in requested for name in ("elo", "elo_poisson")):
        ratings = fit_elo_ratings(
            matches,
            initial_ratings=(
                kwargs.get("initial_ratings")
                if isinstance(kwargs.get("initial_ratings"), Mapping)
                else None
            ),
            base_rating=float(kwargs.get("base_rating", 1500.0)),
            k_factor=float(kwargs.get("k_factor", 20.0)),
            home_advantage=league.home_advantage,
            season_regression=float(kwargs.get("season_regression", 0.15)),
            promotion_gap=float(kwargs.get("promotion_gap", 20.0)),
        )
    if strengths is None and any(
        name in requested for name in ("poisson", "dixon_coles", "bradley_terry")
    ):
        strengths = fit_strengths(
            matches,
            league,
            half_life_days=float(kwargs.get("half_life_days", 365.0)),
            l2=float(kwargs.get("l2", 0.08)),
        )
    for name in requested:
        if name == "elo":
            fitted[name] = EloResultModel(ratings or {}, league)
        elif name == "elo_poisson":
            fitted[name] = EloPoissonModel(ratings or {}, league)
        elif name == "poisson":
            fitted[name] = PoissonModel(strengths or fit_strengths(matches, league))
        elif name == "dixon_coles":
            fitted[name] = DixonColesModel.fit(
                matches,
                league,
                strengths=strengths,
                **fit_kwargs,
            )
        elif name == "bradley_terry":
            fitted[name] = BradleyTerryModel.fit(
                matches,
                league,
                strengths=strengths,
                **fit_kwargs,
            )
    if ensemble_weights:
        selected = {name: fitted[name] for name in ensemble_weights if name in fitted}
        fitted["ensemble"] = EnsembleModel(selected, ensemble_weights)
    return fitted


def _played_matches(matches: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "home_team", "away_team", "home_goals", "away_goals"}
    missing = sorted(required - set(matches.columns))
    if missing:
        raise ValueError(f"Missing model columns: {missing}")
    frame = matches.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="coerce")
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="coerce")
    frame = frame.dropna(
        subset=["home_team", "away_team", "home_goals", "away_goals"]
    )
    frame["home_team"] = frame["home_team"].astype(str)
    frame["away_team"] = frame["away_team"].astype(str)
    return frame


def _all_teams(matches: pd.DataFrame) -> set[str]:
    required = {"home_team", "away_team"}
    if not required.issubset(matches.columns):
        raise ValueError("Missing home_team or away_team")
    return set(matches["home_team"].dropna().astype(str)).union(
        matches["away_team"].dropna().astype(str)
    )


def _recency_weights(dates: pd.Series, half_life_days: float) -> np.ndarray:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    parsed = pd.to_datetime(dates, errors="coerce")
    if parsed.notna().any():
        latest = parsed.max()
        age = (latest - parsed).dt.days.fillna(0).clip(lower=0).to_numpy(dtype=float)
    else:
        age = np.zeros(len(parsed), dtype=float)
    return np.exp(-math.log(2.0) * age / half_life_days)


def _context_neutral(
    neutral: bool,
    context: Mapping[str, object] | None,
) -> bool:
    if context and "neutral" in context:
        return bool(context["neutral"])
    return bool(neutral)


def _poisson_pmf(rate: float) -> np.ndarray:
    goals = np.arange(MAX_GOALS + 1, dtype=float)
    return np.exp(-rate + goals * math.log(rate) - gammaln(goals + 1))


def _independent_poisson_grid(home_rate: float, away_rate: float) -> np.ndarray:
    grid = np.outer(_poisson_pmf(home_rate), _poisson_pmf(away_rate))
    return grid / grid.sum()


def _rescale_wdl(
    grid: np.ndarray,
    home: float,
    draw: float,
    away: float,
) -> np.ndarray:
    targets = np.asarray((home, draw, away), dtype=float)
    if not np.isfinite(targets).all() or (targets < 0).any() or targets.sum() <= 0:
        raise ValueError("Invalid W/D/L probabilities")
    targets /= targets.sum()
    masks = (
        np.tril(np.ones_like(grid, dtype=bool), k=-1),
        np.eye(grid.shape[0], dtype=bool),
        np.triu(np.ones_like(grid, dtype=bool), k=1),
    )
    scaled = np.asarray(grid, dtype=float).copy()
    for mask, target in zip(masks, targets):
        current = float(scaled[mask].sum())
        if current <= 0:
            raise ValueError("Cannot rescale a zero-mass outcome region")
        scaled[mask] *= target / current
    return scaled / scaled.sum()


def _dixon_coles_tau(
    home_goals: int,
    away_goals: int,
    home_rate: float,
    away_rate: float,
    rho: float,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1 - home_rate * away_rate * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + home_rate * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + away_rate * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0
