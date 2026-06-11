"""Fast W/D/L probabilities from independent Poisson rates."""

from __future__ import annotations

from scipy.stats import skellam


def skellam_wdl(lam_h: float, lam_a: float) -> tuple[float, float, float]:
    p_away = float(skellam.cdf(-1, lam_h, lam_a))
    p_draw = float(skellam.pmf(0, lam_h, lam_a))
    p_home = float(1 - p_draw - p_away)
    return p_home, p_draw, p_away
