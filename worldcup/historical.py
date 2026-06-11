"""International match-history download and loading helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from worldcup.team_names import CANONICAL_WC_TEAMS, normalize_intl_team

HISTORY_URLS = {
    "results.csv": "https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
    "shootouts.csv": "https://raw.githubusercontent.com/martj42/international_results/master/shootouts.csv",
}


def download_history(cache: str | Path = "data/wc/historical/") -> dict[str, Path]:
    """Download international results and shootouts into a local cache."""

    cache_path = Path(cache)
    cache_path.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for filename, url in HISTORY_URLS.items():
        path = cache_path / filename
        paths[filename] = path
        if path.exists():
            continue

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                "Unable to download international match history. "
                "Please manually place results.csv and shootouts.csv in "
                f"{cache_path}."
            ) from exc

        path.write_bytes(response.content)

    return paths


def load_history(cache: str | Path = "data/wc/historical/") -> pd.DataFrame:
    """Load normalized international results from the historical cache."""

    results_path = Path(cache) / "results.csv"
    if not results_path.exists():
        raise FileNotFoundError(
            f"Missing {results_path}. Run download_history() or place results.csv "
            "and shootouts.csv in data/wc/historical/."
        )

    history = pd.read_csv(results_path)
    history["date"] = pd.to_datetime(history["date"])
    history["home_team"] = history["home_team"].map(normalize_intl_team)
    history["away_team"] = history["away_team"].map(normalize_intl_team)

    known_home = history["home_team"].isin(CANONICAL_WC_TEAMS)
    known_away = history["away_team"].isin(CANONICAL_WC_TEAMS)
    history = history[known_home | known_away].copy()
    if "neutral" in history:
        history["neutral"] = history["neutral"].astype(bool)

    return history
