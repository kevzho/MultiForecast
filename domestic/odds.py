"""Pre-kickoff bookmaker snapshots and market probability calibration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import math

import numpy as np
import pandas as pd
import requests

from domestic.config import DEFAULT_DATA_ROOT, LeagueConfig, get_league
from domestic.live_data import _resolve, fixture_id
from domestic.models import ScorelineDist

SPORTS = {"premier_league": "soccer_epl", "serie_a": "soccer_italy_serie_a", "ligue_1": "soccer_france_ligue_one", "la_liga": "soccer_spain_la_liga", "bundesliga": "soccer_germany_bundesliga"}
COLUMNS = ("fixture_id", "captured_at", "bookmaker", "market", "selection", "decimal_odds", "opening_or_closing", "source", "source_event_id", "kickoff", "home_team", "away_team")


def load_odds(path: str | Path = Path(DEFAULT_DATA_ROOT) / "odds_snapshots.csv") -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"fixture_id": str, "source_event_id": str})


def fetch_odds(league: str | LeagueConfig, schedule: pd.DataFrame, *, api_key: str, session: requests.Session | None = None, region: str = "uk") -> pd.DataFrame:
    config = get_league(league)
    response = (session or requests).get(
        f"https://api.the-odds-api.com/v4/sports/{SPORTS[config.slug]}/odds/",
        params={"apiKey": api_key, "regions": region, "markets": "h2h,totals", "oddsFormat": "decimal"}, timeout=25,
    )
    response.raise_for_status()
    captured = datetime.now(timezone.utc)
    teams = set(schedule.home_team) | set(schedule.away_team)
    fixture_lookup = {(row.home_team, row.away_team): row for row in schedule.itertuples(index=False)}
    events = response.json()
    rows = []
    for event in events:
        home = _resolve(event.get("home_team", ""), teams, config)
        away = _resolve(event.get("away_team", ""), teams, config)
        fixture = fixture_lookup.get((home, away))
        if fixture is None:
            continue
        kickoff = pd.Timestamp(event["commence_time"])
        if kickoff.tzinfo is None:
            kickoff = kickoff.tz_localize("UTC")
        if kickoff <= pd.Timestamp(captured):
            continue
        id_ = fixture_id(config.slug, config.season, home, away)
        bookmakers = list(event.get("bookmakers", []))
        # BTTS is an additional, per-event market. Limit calls to imminent fixtures.
        if (kickoff - pd.Timestamp(captured)).total_seconds() <= 3 * 3600:
            try:
                extra = (session or requests).get(
                    f"https://api.the-odds-api.com/v4/sports/{SPORTS[config.slug]}/events/{event['id']}/odds/",
                    params={"apiKey": api_key, "regions": region, "markets": "btts", "oddsFormat": "decimal"}, timeout=25,
                )
                extra.raise_for_status()
                bookmakers.extend(extra.json().get("bookmakers", []))
            except requests.RequestException:
                pass
        for bookmaker in bookmakers:
            for market in bookmaker.get("markets", []):
                if market.get("key") not in ("h2h", "totals", "btts"):
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 1:
                        continue
                    if market["key"] == "h2h":
                        selection = "home" if outcome["name"] == event["home_team"] else "away" if outcome["name"] == event["away_team"] else "draw" if outcome["name"].casefold() == "draw" else None
                        market_name = "1x2"
                    elif market["key"] == "totals":
                        point = outcome.get("point")
                        selection = ("over" if outcome["name"].casefold() == "over" else "under") if point == 2.5 else None
                        market_name = "totals_2_5"
                    else:
                        selection = outcome["name"].casefold() if outcome["name"].casefold() in ("yes", "no") else None
                        market_name = "btts"
                    if selection is None:
                        continue
                    rows.append((id_, captured.isoformat(), bookmaker["key"], market_name, selection, float(price), "snapshot", "the-odds-api", str(event["id"]), kickoff.isoformat(), home, away))
    return pd.DataFrame(rows, columns=COLUMNS)


def append_snapshots(new: pd.DataFrame, *, path: str | Path = Path(DEFAULT_DATA_ROOT) / "odds_snapshots.csv") -> pd.DataFrame:
    old = load_odds(path)
    if new.empty:
        return old
    new = new.copy()
    key = ["fixture_id", "bookmaker", "market", "selection"]
    latest = old.sort_values("captured_at").drop_duplicates(key, keep="last") if not old.empty else old
    previous = {tuple(getattr(row, field) for field in key): row for row in latest.itertuples(index=False)}
    new = new[[
        (previous.get(tuple(getattr(row, field) for field in key)) is None)
        or (previous[tuple(getattr(row, field) for field in key)].decimal_odds != row.decimal_odds)
        or ((pd.Timestamp(row.kickoff) - pd.Timestamp(row.captured_at)).total_seconds() <= 900 and previous[tuple(getattr(row, field) for field in key)].opening_or_closing != "closing")
        for row in new.itertuples(index=False)
    ]].copy()
    if new.empty:
        return old
    existing_ids = set(old.fixture_id) if not old.empty else set()
    new.loc[~new.fixture_id.isin(existing_ids), "opening_or_closing"] = "opening"
    kickoff = pd.to_datetime(new.kickoff, utc=True)
    capture = pd.to_datetime(new.captured_at, utc=True)
    new.loc[(kickoff - capture).dt.total_seconds().between(0, 900), "opening_or_closing"] = "closing"
    combined = pd.concat([old, new], ignore_index=True) if not old.empty else new.reset_index(drop=True)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    combined.to_csv(temp, index=False)
    temp.replace(target)
    return combined


def consensus_1x2(snapshots: pd.DataFrame, fixture: str, *, before: str | pd.Timestamp | None = None) -> tuple[np.ndarray, dict[str, float]] | None:
    frame = snapshots[(snapshots.fixture_id == fixture) & (snapshots.market == "1x2")].copy()
    if frame.empty:
        return None
    frame["captured_at"] = pd.to_datetime(frame.captured_at, utc=True, errors="coerce")
    frame["kickoff"] = pd.to_datetime(frame.kickoff, utc=True, errors="coerce")
    frame = frame[(frame.captured_at < frame.kickoff) & frame.captured_at.notna()]
    if before is not None:
        frame = frame[frame.captured_at < pd.Timestamp(before).tz_localize("UTC") if pd.Timestamp(before).tzinfo is None else frame.captured_at < pd.Timestamp(before)]
    if frame.empty:
        return None
    frame = frame.sort_values("captured_at").drop_duplicates(["bookmaker", "selection"], keep="last")
    complete = []
    for _, book in frame.groupby("bookmaker"):
        prices = book.set_index("selection").decimal_odds.to_dict()
        if all(name in prices for name in ("home", "draw", "away")):
            raw = np.array([1 / float(prices[name]) for name in ("home", "draw", "away")])
            complete.append(raw / raw.sum())
    if not complete:
        return None
    mean = np.mean(complete, axis=0)
    prices = frame.groupby("selection").decimal_odds.max().to_dict()
    return mean / mean.sum(), prices


def blend_grid(grid: np.ndarray, market: np.ndarray, weight: float) -> ScorelineDist:
    base = ScorelineDist(grid).wdl
    target = (1 - weight) * np.asarray(base) + weight * market
    masks = np.indices(grid.shape)
    regions = (masks[0] > masks[1], masks[0] == masks[1], masks[0] < masks[1])
    blended = grid.copy()
    for mask, goal in zip(regions, target):
        blended[mask] *= goal / blended[mask].sum()
    return ScorelineDist(blended / blended.sum())


class OddsAwareModel:
    name = "odds_aware"

    def __init__(self, base: object, markets: dict[tuple[str, str], np.ndarray], weight: float):
        self.base, self.markets, self.weight = base, markets, weight

    def predict(self, home: str, away: str, **kwargs: object) -> ScorelineDist:
        base = self.base.predict(home, away, **kwargs)
        market = self.markets.get((home, away))
        return blend_grid(base.grid, market, self.weight) if market is not None else base


def calibrate_market_weight(matches: pd.DataFrame, snapshots: pd.DataFrame, league: str | LeagueConfig, model_name: str, *, minimum_training: int = 30, minimum_holdout: int = 10) -> dict:
    """Fit a blend on past walk-forward predictions; reserve the latest season."""
    from domestic.validation import rolling_backtest
    config = get_league(league)
    if snapshots.empty:
        return {"weight": 0.0, "reason": "No historical pre-kickoff odds"}
    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    if played.empty:
        return {"weight": 0.0, "reason": "No real completed matches"}
    first = pd.to_datetime(snapshots.captured_at, errors="coerce", utc=True).min()
    if pd.isna(first):
        return {"weight": 0.0, "reason": "No valid odds timestamps"}
    result = rolling_backtest(model_name, played, config, since=first.tz_localize(None), min_train_matches=max(100, config.expected_matches * 2), refit_every=max(100, config.expected_matches // 2))
    rows = []
    season_lookup = {(pd.Timestamp(r.date), r.home_team, r.away_team): str(r.season) for r in played.itertuples(index=False)}
    for row in result.predictions.itertuples(index=False):
        season = season_lookup.get((pd.Timestamp(row.date), row.home_team, row.away_team))
        if not season:
            continue
        fixture = fixture_id(config.slug, season, row.home_team, row.away_team)
        market = consensus_1x2(snapshots, fixture)
        if market is None:
            continue
        actual = ("home", "draw", "away").index(row.actual)
        rows.append((season, np.array([row.p_home, row.p_draw, row.p_away]), market[0], actual))
    completed_seasons = sorted({row[0] for row in rows if row[0] < config.season})
    if len(completed_seasons) < 2:
        return {"weight": 0.0, "reason": "Need pre-match odds across at least two completed seasons", "samples": len(rows)}
    holdout_season = completed_seasons[-1]
    train = [row for row in rows if row[0] < holdout_season]
    holdout = [row for row in rows if row[0] == holdout_season]
    if len(train) < minimum_training or len(holdout) < minimum_holdout:
        return {"weight": 0.0, "reason": "Insufficient training or untouched holdout matches", "trainingSamples": len(train), "holdoutSamples": len(holdout)}
    def loss(sample: list, weight: float) -> float:
        return float(np.mean([-math.log(max(((1 - weight) * base + weight * market)[actual], 1e-12)) for _, base, market, actual in sample]))
    def brier(sample: list, weight: float) -> float:
        return float(np.mean([np.square((1 - weight) * base + weight * market - np.eye(3)[actual]).sum() for _, base, market, actual in sample]))
    def calibration_error(sample: list, weight: float) -> float:
        probabilities = np.array([(1 - weight) * base + weight * market for _, base, market, _ in sample]).ravel()
        outcomes = np.array([np.eye(3)[actual] for _, _, _, actual in sample]).ravel()
        bins = np.minimum((probabilities * 10).astype(int), 9)
        return float(sum(np.abs(probabilities[bins == index].mean() - outcomes[bins == index].mean()) * (bins == index).sum() for index in range(10) if (bins == index).any()) / len(probabilities))
    weight = min(np.linspace(0, 1, 21), key=lambda candidate: loss(train, float(candidate)))
    base_loss = loss(holdout, 0.0)
    blended_loss = loss(holdout, float(weight))
    # A blend that loses to the base model on untouched data is not activated.
    active = blended_loss < base_loss
    return {"weight": float(weight) if active else 0.0, "candidateWeight": float(weight), "trainingSamples": len(train), "holdoutSamples": len(holdout), "holdoutSeason": holdout_season, "holdoutBaseLogLoss": base_loss, "holdoutBlendLogLoss": blended_loss, "holdoutBaseBrier": brier(holdout, 0.0), "holdoutBlendBrier": brier(holdout, float(weight)), "holdoutBaseCalibrationError": calibration_error(holdout, 0.0), "holdoutBlendCalibrationError": calibration_error(holdout, float(weight)), "reason": "Validated on untouched season" if active else "Blend did not improve untouched holdout"}


def consensus_binary(snapshots: pd.DataFrame, fixture: str, market: str, *, before: str | pd.Timestamp | None = None) -> tuple[dict[str, float], dict[str, float]] | None:
    selections = {"totals_2_5": ("over", "under"), "btts": ("yes", "no")}.get(market)
    if selections is None:
        raise ValueError(f"Unsupported binary market: {market}")
    frame = snapshots[(snapshots.fixture_id == fixture) & (snapshots.market == market)].copy()
    if frame.empty:
        return None
    frame["captured_at"] = pd.to_datetime(frame.captured_at, utc=True, errors="coerce")
    frame["kickoff"] = pd.to_datetime(frame.kickoff, utc=True, errors="coerce")
    frame = frame[(frame.captured_at < frame.kickoff) & frame.captured_at.notna()]
    if before is not None:
        cutoff = pd.Timestamp(before)
        frame = frame[frame.captured_at < (cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff)]
    if frame.empty:
        return None
    frame = frame.sort_values("captured_at").drop_duplicates(["bookmaker", "selection"], keep="last")
    complete = []
    for _, book in frame.groupby("bookmaker"):
        prices = book.set_index("selection").decimal_odds.to_dict()
        if all(key in prices for key in selections):
            raw = np.array([1 / float(prices[key]) for key in selections])
            complete.append(raw / raw.sum())
    if not complete:
        return None
    mean = np.mean(complete, axis=0)
    return dict(zip(selections, map(float, mean / mean.sum()))), frame.groupby("selection").decimal_odds.max().to_dict()
