"""Recency-weighted international attack and defense strengths."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
import pandas as pd

from worldcup.data import load_elo
from worldcup.historical import download_history, load_history
from worldcup.team_names import CANONICAL_WC_TEAMS, normalize_intl_team

TOURNAMENT_COMPETITIVENESS_FACTORS = {
    "world cup qualification": 0.8,
    "fifa world cup qualification": 0.8,
    "uefa euro qualification": 0.8,
    "afc asian cup qualification": 0.8,
    "africa cup of nations qualification": 0.8,
    "concacaf championship qualification": 0.8,
    "concacaf gold cup qualification": 0.8,
    "copa américa qualification": 0.8,
    "copa america qualification": 0.8,
    "nations league": 0.8,
    "friendly": 0.4,
    "fifa world cup": 1.0,
    "world cup": 1.0,
    "uefa euro": 1.0,
    "european championship": 1.0,
    "copa américa": 1.0,
    "copa america": 1.0,
    "afc asian cup": 1.0,
    "africa cup of nations": 1.0,
    "concacaf gold cup": 1.0,
    "copa libertadores": 1.0,
    "confederations cup": 1.0,
}
UNKNOWN_TOURNAMENT_FACTOR = 0.7
DEFAULT_ELO_SHRINKAGE_ALPHA = 0.30


@dataclass(frozen=True)
class StrengthTable:
    attack: dict[str, float]
    defense: dict[str, float]
    base_rate: float
    home_adv: float

    def expected_goals(
        self,
        home: str,
        away: str,
        neutral: bool = False,
    ) -> tuple[float, float]:
        home = normalize_intl_team(home)
        away = normalize_intl_team(away)
        home_adv = 0.0 if neutral else self.home_adv
        lam_h = math.exp(
            self.base_rate
            + self.attack.get(home, 0.0)
            + self.defense.get(away, 0.0)
            + home_adv
        )
        lam_a = math.exp(
            self.base_rate
            + self.attack.get(away, 0.0)
            + self.defense.get(home, 0.0)
        )
        return float(max(lam_h, 1e-6)), float(max(lam_a, 1e-6))


def fit_strengths(
    history: pd.DataFrame,
    half_life_days: int = 365,
    max_years: int = 8,
    elo_shrinkage_alpha: float = DEFAULT_ELO_SHRINKAGE_ALPHA,
) -> StrengthTable:
    """Fit recency-weighted Poisson attack/defense strengths."""

    if history.empty:
        return _elo_fallback_table()

    matches = _prepare_matches(history, max_years=max_years)
    if matches.empty:
        return _elo_fallback_table()

    rows = _goal_rows(matches, half_life_days=half_life_days)
    teams = sorted(set(matches["home_team"]).union(matches["away_team"]))
    if not rows.empty and len(teams) >= 2:
        table = _fit_glm(rows, teams)
    else:
        table = StrengthTable({}, {}, math.log(1.25), 0.0)

    match_counts = _match_counts(matches)
    target_teams = _target_teams(matches)
    attack, defense = _blend_with_elo(
        table.attack,
        table.defense,
        match_counts,
        target_teams,
        elo_shrinkage_alpha=elo_shrinkage_alpha,
    )
    base_rate = table.base_rate
    attack, defense, base_rate = _center_strengths(attack, defense, base_rate)
    return StrengthTable(attack, defense, base_rate, table.home_adv)


def save_strengths(table: StrengthTable, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    teams = sorted(set(table.attack).union(table.defense))
    rows = [
        {
            "Team": team,
            "Attack": table.attack.get(team, 0.0),
            "Defense": table.defense.get(team, 0.0),
            "BaseRate": table.base_rate,
            "HomeAdv": table.home_adv,
        }
        for team in teams
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def load_strengths(path: str | Path) -> StrengthTable:
    strengths = pd.read_csv(path)
    attack = dict(zip(strengths["Team"], strengths["Attack"].astype(float)))
    defense = dict(zip(strengths["Team"], strengths["Defense"].astype(float)))
    base_rate = float(strengths["BaseRate"].iloc[0])
    home_adv = float(strengths["HomeAdv"].iloc[0])
    return StrengthTable(attack, defense, base_rate, home_adv)


def _prepare_matches(history: pd.DataFrame, max_years: int) -> pd.DataFrame:
    matches = history.copy()
    matches["date"] = pd.to_datetime(matches["date"])
    matches["home_team"] = matches["home_team"].map(normalize_intl_team)
    matches["away_team"] = matches["away_team"].map(normalize_intl_team)
    matches = matches.dropna(
        subset=["date", "home_team", "away_team", "home_score", "away_score"]
    )
    latest = matches["date"].max()
    cutoff = latest - pd.DateOffset(years=max_years)
    matches = matches[matches["date"] >= cutoff].copy()
    if "neutral" not in matches:
        matches["neutral"] = False
    if "tournament" not in matches:
        matches["tournament"] = ""
    matches["neutral"] = matches["neutral"].astype(bool)
    matches["tournament"] = matches["tournament"].fillna("").astype(str)
    return matches


def _goal_rows(matches: pd.DataFrame, half_life_days: int) -> pd.DataFrame:
    latest = matches["date"].max()
    age_days = (latest - matches["date"]).dt.days.clip(lower=0)
    recency_weights = np.exp(-math.log(2) * age_days / half_life_days)
    competitiveness = matches["tournament"].map(_competitiveness_factor).astype(float)
    weights = recency_weights * competitiveness
    opponent_factors = _opponent_quality_factors(matches)

    home_rows = pd.DataFrame(
        {
            "goals": matches["home_score"].astype(float),
            "scorer": matches["home_team"],
            "conceder": matches["away_team"],
            "home": (~matches["neutral"]).astype(int),
            "weight": weights * opponent_factors["away"].to_numpy(),
        }
    )
    away_rows = pd.DataFrame(
        {
            "goals": matches["away_score"].astype(float),
            "scorer": matches["away_team"],
            "conceder": matches["home_team"],
            "home": 0,
            "weight": weights * opponent_factors["home"].to_numpy(),
        }
    )
    return pd.concat([home_rows, away_rows], ignore_index=True)


def _competitiveness_factor(tournament: str) -> float:
    tournament_key = str(tournament).strip().lower()
    for pattern, factor in TOURNAMENT_COMPETITIVENESS_FACTORS.items():
        if pattern in tournament_key:
            return factor
    return UNKNOWN_TOURNAMENT_FACTOR


def _opponent_quality_factors(matches: pd.DataFrame) -> pd.DataFrame:
    elo = {normalize_intl_team(team): float(rating) for team, rating in load_elo().items()}
    mean_elo = float(np.mean(list(elo.values()))) if elo else 1500.0

    def factor(team: str) -> float:
        rating = elo.get(normalize_intl_team(team), mean_elo)
        # Opponent normalization: 1.0 + one point per 800 Elo above the WC mean,
        # clipped to [0.5, 1.2]. This reduces confederation schedule imbalance:
        # CONMEBOL/UEFA teams facing stronger opponents receive more credit than
        # teams compiling similar scorelines against substantially weaker slates.
        return float(np.clip(1.0 + (rating - mean_elo) / 800, 0.5, 1.2))

    return pd.DataFrame(
        {
            "home": matches["home_team"].map(factor).astype(float),
            "away": matches["away_team"].map(factor).astype(float),
        },
        index=matches.index,
    )


def _fit_glm(rows: pd.DataFrame, teams: list[str]) -> StrengthTable:
    try:
        import statsmodels.api as sm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "statsmodels is required to fit strengths; run `pip install statsmodels`. "
            "Pre-fitted data/wc/intl_strengths.csv is used at runtime and does not need statsmodels."
        ) from exc

    attack_cols = pd.get_dummies(rows["scorer"], prefix="attack", dtype=float)
    defense_cols = pd.get_dummies(rows["conceder"], prefix="defense", dtype=float)
    attack_ref = f"attack_{teams[-1]}"
    defense_ref = f"defense_{teams[-1]}"
    attack_cols = attack_cols.drop(columns=[attack_ref], errors="ignore")
    defense_cols = defense_cols.drop(columns=[defense_ref], errors="ignore")
    exog = pd.concat([rows[["home"]].astype(float), attack_cols, defense_cols], axis=1)
    exog = sm.add_constant(exog, has_constant="add")

    result = sm.GLM(
        rows["goals"].astype(float),
        exog.astype(float),
        family=sm.families.Poisson(),
        freq_weights=rows["weight"].astype(float),
    ).fit()

    params = result.params
    attack = {
        team: float(params.get(f"attack_{team}", 0.0))
        for team in teams
    }
    defense = {
        team: float(params.get(f"defense_{team}", 0.0))
        for team in teams
    }
    base_rate = float(params["const"])
    attack, defense, base_rate = _center_strengths(attack, defense, base_rate)
    return StrengthTable(attack, defense, base_rate, float(params.get("home", 0.0)))


def _match_counts(matches: pd.DataFrame) -> dict[str, int]:
    counts = pd.concat([matches["home_team"], matches["away_team"]]).value_counts()
    return {str(team): int(count) for team, count in counts.items()}


def _target_teams(matches: pd.DataFrame) -> set[str]:
    observed = set(matches["home_team"]).union(matches["away_team"])
    if observed & CANONICAL_WC_TEAMS:
        return set(CANONICAL_WC_TEAMS)
    return set(observed)


def _blend_with_elo(
    attack: dict[str, float],
    defense: dict[str, float],
    match_counts: dict[str, int],
    target_teams: set[str],
    elo_shrinkage_alpha: float = DEFAULT_ELO_SHRINKAGE_ALPHA,
) -> tuple[dict[str, float], dict[str, float]]:
    elo_attack, elo_defense = _elo_implied_strengths()
    alpha = float(np.clip(elo_shrinkage_alpha, 0.0, 1.0))
    teams = sorted(target_teams)
    blended_attack: dict[str, float] = {}
    blended_defense: dict[str, float] = {}
    for team in teams:
        reliability = min(match_counts.get(team, 0) / 10, 1.0)
        reliability_attack = (
            reliability * attack.get(team, 0.0)
            + (1 - reliability) * elo_attack.get(team, 0.0)
        )
        reliability_defense = (
            reliability * defense.get(team, 0.0)
            + (1 - reliability) * elo_defense.get(team, 0.0)
        )
        blended_attack[team] = (
            (1 - alpha) * reliability_attack + alpha * elo_attack.get(team, 0.0)
        )
        blended_defense[team] = (
            (1 - alpha) * reliability_defense + alpha * elo_defense.get(team, 0.0)
        )
    return blended_attack, blended_defense


def _elo_implied_strengths() -> tuple[dict[str, float], dict[str, float]]:
    elo = {normalize_intl_team(team): float(rating) for team, rating in load_elo().items()}
    mean_elo = float(np.mean(list(elo.values())))
    log_scale = math.log(10) / 800
    attack = {team: (rating - mean_elo) * log_scale / 2 for team, rating in elo.items()}
    defense = {team: -(rating - mean_elo) * log_scale / 2 for team, rating in elo.items()}
    return attack, defense


def _center_strengths(
    attack: dict[str, float],
    defense: dict[str, float],
    base_rate: float,
) -> tuple[dict[str, float], dict[str, float], float]:
    if not attack or not defense:
        return attack, defense, base_rate
    attack_mean = float(np.mean(list(attack.values())))
    defense_mean = float(np.mean(list(defense.values())))
    centered_attack = {team: value - attack_mean for team, value in attack.items()}
    centered_defense = {team: value - defense_mean for team, value in defense.items()}
    return centered_attack, centered_defense, base_rate + attack_mean + defense_mean


def _elo_fallback_table() -> StrengthTable:
    attack, defense = _elo_implied_strengths()
    attack, defense, base_rate = _center_strengths(attack, defense, math.log(1.25))
    return StrengthTable(attack, defense, base_rate, 0.0)


def _print_rankings(table: StrengthTable) -> None:
    attack_rank = sorted(table.attack.items(), key=lambda item: item[1], reverse=True)
    defense_rank = sorted(table.defense.items(), key=lambda item: item[1])
    print("Top attack:")
    for team, value in attack_rank[:5]:
        print(f"  {team}: {value:.3f}")
    print("Bottom attack:")
    for team, value in attack_rank[-5:]:
        print(f"  {team}: {value:.3f}")
    print("Top defense:")
    for team, value in defense_rank[:5]:
        print(f"  {team}: {value:.3f}")
    print("Bottom defense:")
    for team, value in defense_rank[-5:]:
        print(f"  {team}: {value:.3f}")


def _overall_rankings(table: StrengthTable) -> list[tuple[str, float]]:
    teams = sorted(set(table.attack).union(table.defense))
    return sorted(
        ((team, table.attack.get(team, 0.0) - table.defense.get(team, 0.0)) for team in teams),
        key=lambda item: item[1],
        reverse=True,
    )


def _print_overall_report(before: StrengthTable | None, after: StrengthTable) -> None:
    after_rankings = _overall_rankings(after)
    print("Top 10 overall strength (attack - defense):")
    for idx, (team, value) in enumerate(after_rankings[:10], start=1):
        print(f"  {idx:2d}. {team}: {value:.3f}")

    before_lookup = {}
    if before is not None:
        before_lookup = {
            team: idx
            for idx, (team, _) in enumerate(_overall_rankings(before), start=1)
        }
    after_lookup = {team: idx for idx, (team, _) in enumerate(after_rankings, start=1)}
    print("Spain/Argentina rank change:")
    for team in ("Spain", "Argentina"):
        before_rank = before_lookup.get(team, "n/a")
        after_rank = after_lookup.get(team, "n/a")
        print(f"  {team}: before {before_rank}, after {after_rank}")


def _print_backtest_report(
    before: StrengthTable | None,
    after: StrengthTable,
    history: pd.DataFrame,
) -> None:
    if before is None:
        print("Dixon-Coles backtest before/after: no previous strengths CSV found.")
        return
    try:
        from worldcup.models.dixon_coles import DixonColesModel
        from worldcup.validation import backtest
    except ModuleNotFoundError as exc:
        print(f"Dixon-Coles backtest unavailable: {exc}")
        return

    before_metrics = backtest(lambda: DixonColesModel(before), history)
    after_metrics = backtest(lambda: DixonColesModel(after), history)
    print("Dixon-Coles backtest (since 2018):")
    print(
        "  Before: "
        f"LogLoss={before_metrics['logloss']:.4f}, RPS={before_metrics['rps']:.4f}"
    )
    print(
        "  After:  "
        f"LogLoss={after_metrics['logloss']:.4f}, RPS={after_metrics['rps']:.4f}"
    )


def main() -> None:
    output_path = Path("data/wc/intl_strengths.csv")
    previous_table = load_strengths(output_path) if output_path.exists() else None
    download_history()
    history = load_history()
    table = fit_strengths(history)
    _print_rankings(table)
    _print_overall_report(previous_table, table)
    _print_backtest_report(previous_table, table, history)
    save_strengths(table, output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
