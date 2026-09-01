from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domestic.config import (
    LeagueConfig,
    data_paths,
    get_league,
    list_leagues,
    previous_season_codes,
    season_code,
)
from domestic.data import (
    CANONICAL_COLUMNS,
    fetch_matches,
    load_history,
    load_matches,
    normalize_team,
    season_rollover,
    validate_matches,
)
from domestic.models import (
    MODEL_NAMES,
    BradleyTerryModel,
    DixonColesModel,
    EloPoissonModel,
    EnsembleModel,
    PoissonModel,
    ScorelineDist,
    StrengthTable,
    fit_models,
    rollover_ratings,
)
from domestic.validation import (
    brier_score,
    compare_models,
    derive_ensemble_weights,
    fit_selected_model,
    log_loss,
    ranked_probability_score,
    rolling_backtest,
    select_model,
)


def _small_config() -> LeagueConfig:
    return LeagueConfig(
        slug="test_league",
        name="Test League",
        country="Testland",
        code="T1",
        team_count=4,
        home_advantage=65,
        draw_rate=0.25,
        avg_goals=2.7,
        champions_league_positions=(1,),
        europa_league_positions=(2,),
        conference_league_positions=(),
        relegation_positions=(4,),
    )


def _matches(seasons: tuple[str, ...] = ("2324", "2425", "2526")) -> pd.DataFrame:
    teams = ("Alpha", "Bravo", "Charlie", "Delta")
    strengths = {"Alpha": 1.2, "Bravo": 0.5, "Charlie": -0.1, "Delta": -0.8}
    rows = []
    date = pd.Timestamp("2023-08-01")
    rng = np.random.default_rng(2627)
    for season in seasons:
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                home_rate = np.exp(0.25 + 0.28 * strengths[home] - 0.18 * strengths[away])
                away_rate = np.exp(0.05 + 0.28 * strengths[away] - 0.18 * strengths[home])
                rows.append(
                    {
                        "league": "test_league",
                        "season": season,
                        "date": date,
                        "home_team": home,
                        "away_team": away,
                        "home_goals": int(rng.poisson(home_rate)),
                        "away_goals": int(rng.poisson(away_rate)),
                        "status": "played",
                        "source_updated_at": pd.Timestamp("2026-08-27", tz="UTC"),
                    }
                )
                date += timedelta(days=4)
    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)


def test_big_five_configuration_and_paths(tmp_path):
    leagues = list_leagues()
    assert {league.code for league in leagues} == {"E0", "I1", "F1", "SP1", "D1"}
    assert {league.season for league in leagues} == {"2627"}
    assert get_league("Premier League").slug == "premier_league"
    assert get_league("SP1").slug == "la_liga"
    assert get_league("Bundesliga").team_count == 18
    assert get_league("Ligue 1").expected_matches == 306
    assert get_league("Premier League").standings_tiebreakers == (
        "points",
        "goal_difference",
        "goals_for",
    )

    paths = data_paths("E0", "2026/27", tmp_path)
    assert paths.raw == tmp_path / "domestic" / "raw" / "2627" / "E0.csv"
    assert paths.processed.name == "premier_league.csv"
    assert paths.last_known_good.parts[-3] == "last_known_good"
    assert season_code("2026-2027") == "2627"
    assert previous_season_codes("2627", 2) == ("2425", "2526", "2627")


def test_alias_normalization_and_rollover():
    assert normalize_team("Man Utd", "E0") == "Manchester United"
    assert normalize_team("Paris SG", "F1") == "Paris Saint-Germain"
    assert normalize_team("M'gladbach", "D1") == "Borussia Monchengladbach"
    assert normalize_team("Unknown FC", "I1") == "Unknown FC"

    previous = pd.DataFrame({"home_team": ["A", "B"], "away_team": ["B", "C"]})
    rollover = season_rollover(previous, current_teams=("A", "B", "D"))
    assert rollover.returning == ("A", "B")
    assert rollover.promoted == ("D",)
    assert rollover.relegated == ("C",)


def test_validation_rejects_duplicates_and_supports_partial_seasons():
    config = _small_config()
    matches = _matches(("2526",))
    report = validate_matches(matches, config, strict=True)
    assert report.valid
    assert report.stats == {"matches": 12, "played": 12, "scheduled": 0, "teams": 4}

    partial = matches.iloc[:3]
    assert validate_matches(partial, config).valid
    assert not validate_matches(partial, config, strict=True).valid

    duplicate = pd.concat([matches, matches.iloc[[0]]], ignore_index=True)
    invalid = validate_matches(duplicate, config)
    assert not invalid.valid
    assert any("Duplicate" in error for error in invalid.errors)


class _Response:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self, content: bytes | None = None, error: Exception | None = None):
        self.content = content
        self.error = error

    def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return _Response(self.content or b"")


def test_fetch_uses_last_known_good_without_overwriting_it(tmp_path):
    raw = (
        b"Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
        b"16/08/2026,Man United,Man City,2,1\n"
        b"23/08/2026,Man City,Man United,,\n"
    )
    fresh = fetch_matches("E0", "2627", data_root=tmp_path, session=_Session(raw))
    assert list(fresh.columns) == list(CANONICAL_COLUMNS)
    assert fresh.attrs["data_source"] == "remote"
    assert fresh.iloc[0]["home_team"] == "Manchester United"

    paths = data_paths("E0", "2627", tmp_path)
    cached_bytes = paths.last_known_good.read_bytes()
    cached = fetch_matches(
        "E0",
        "2627",
        data_root=tmp_path,
        session=_Session(error=requests.ConnectionError("offline")),
    )
    assert cached.attrs["data_source"] == "last_known_good"
    assert cached.attrs["used_cache"] is True
    assert paths.last_known_good.read_bytes() == cached_bytes

    malformed = fetch_matches(
        "E0",
        "2627",
        data_root=tmp_path,
        session=_Session(b"wrong,columns\n1,2\n"),
    )
    assert malformed.attrs["data_source"] == "last_known_good"
    assert paths.last_known_good.read_bytes() == cached_bytes


def test_loaders_discover_legacy_and_canonical_history(tmp_path):
    legacy = tmp_path / "E0_2526.csv"
    legacy.write_text(
        "Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/08/2025,Man City,Man United,1,0\n",
        encoding="utf-8",
    )
    loaded = load_matches("E0", "2526", data_root=tmp_path)
    assert loaded.iloc[0]["home_team"] == "Manchester City"
    assert loaded.iloc[0]["status"] == "played"

    paths = data_paths("E0", "2627", tmp_path)
    paths.processed.parent.mkdir(parents=True)
    current = loaded.copy()
    current["season"] = "2627"
    current["date"] = pd.Timestamp("2026-08-01")
    current.to_csv(paths.processed, index=False)
    history = load_history("E0", seasons=("2526", "2627"), data_root=tmp_path)
    assert tuple(history["season"]) == ("2526", "2627")


def test_rollover_ratings_regresses_returning_and_seeds_promoted():
    ratings = rollover_ratings(
        {"Alpha": 1600, "Bravo": 1450, "Relegated": 1400},
        ("Alpha", "Bravo", "Promoted"),
        promoted=("Promoted",),
        regression=0.2,
    )
    assert ratings["Alpha"] == 1580
    assert ratings["Bravo"] == 1460
    assert ratings["Promoted"] < ratings["Bravo"]
    assert "Relegated" not in ratings


def test_scoreline_distribution_breakdown_and_sampling():
    grid = np.zeros((11, 11))
    grid[1, 0] = 0.5
    grid[1, 1] = 0.3
    grid[0, 1] = 0.2
    dist = ScorelineDist(grid)
    assert dist.wdl == pytest.approx((0.5, 0.3, 0.2))
    assert dist.expected_goals == pytest.approx((0.8, 0.5))
    assert dist.both_teams_to_score == pytest.approx(0.3)
    assert dist.top_scorelines(2)[0] == (1, 0, 0.5)
    assert dist.sample(np.random.default_rng(2)) in {(1, 0), (1, 1), (0, 1)}

    with pytest.raises(ValueError):
        ScorelineDist(np.ones((10, 10)) / 100)


def test_all_registered_models_return_valid_distributions():
    config = _small_config()
    matches = _matches()
    models = fit_models(matches, config)
    assert tuple(models) == MODEL_NAMES
    for model in models.values():
        dist = model.predict("Alpha", "Delta")
        assert isinstance(dist, ScorelineDist)
        assert dist.grid.shape == (11, 11)
        assert dist.grid.sum() == pytest.approx(1)
        assert sum(dist.wdl) == pytest.approx(1)
        assert all(0 <= probability <= 1 for probability in dist.wdl)

    elo = models["elo_poisson"]
    assert isinstance(elo, EloPoissonModel)
    assert elo.predict("Alpha", "Delta").wdl[0] > elo.predict("Delta", "Alpha").wdl[0]
    assert isinstance(models["dixon_coles"], DixonColesModel)
    assert isinstance(models["bradley_terry"], BradleyTerryModel)


def test_dixon_coles_adjustment_and_equal_weight_ensemble():
    strengths = StrengthTable(
        attack={"A": 0.2, "B": -0.2},
        defense={"A": -0.1, "B": 0.1},
        base_rate=0.1,
        home_advantage=0.15,
    )
    poisson = fit_models(_matches(), _small_config(), names=("poisson",))["poisson"]
    dc = DixonColesModel(strengths, rho=-0.12)
    base = PoissonModel(strengths).predict("A", "B").grid
    adjusted = dc.predict("A", "B").grid
    assert adjusted[0, 0] > base[0, 0]
    assert adjusted[1, 1] > base[1, 1]

    ensemble = EnsembleModel((poisson, dc))
    expected = (poisson.predict("A", "B").grid + dc.predict("A", "B").grid) / 2
    assert np.allclose(ensemble.predict("A", "B").grid, expected)


def test_walk_forward_metrics_selection_and_final_fit():
    matches = _matches()
    config = _small_config()
    result = rolling_backtest(
        "elo",
        matches,
        config,
        min_train_matches=12,
        refit_every=12,
        calibration_bins=5,
    )
    assert result.n_predictions == 24
    assert result.logloss > 0
    assert result.brier >= 0
    assert 0 <= result.rps <= 1
    assert result.calibration_bins
    assert log_loss((0.5, 0.3, 0.2), 0) == pytest.approx(-np.log(0.5))
    assert brier_score((1, 0, 0), 0) == pytest.approx(0)
    assert ranked_probability_score((1, 0, 0), 0) == pytest.approx(0)

    comparison = compare_models(
        ("elo", "elo_poisson"),
        matches,
        config,
        min_train_matches=12,
        refit_every=50,
    )
    champion = select_model(comparison)
    assert champion in {"elo", "elo_poisson"}
    weights = derive_ensemble_weights(comparison, top_n=2)
    assert sum(weights.values()) == pytest.approx(1)
    selected = fit_selected_model(matches, config, comparison)
    ensemble = fit_selected_model(matches, config, comparison, ensemble=True, ensemble_top_n=2)
    assert selected.predict("Alpha", "Delta").grid.sum() == pytest.approx(1)
    assert ensemble.predict("Alpha", "Delta").grid.sum() == pytest.approx(1)
