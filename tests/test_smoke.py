import builtins
import importlib
import math
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _Tab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _block_statsmodels(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "statsmodels" or name.startswith("statsmodels."):
            raise ModuleNotFoundError("No module named 'statsmodels'")
        return real_import(name, *args, **kwargs)

    for module_name in list(sys.modules):
        if module_name == "statsmodels" or module_name.startswith("statsmodels."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)
    monkeypatch.setattr(builtins, "__import__", guarded_import)


def _install_streamlit_stub(monkeypatch, calls):
    streamlit = types.SimpleNamespace()

    def set_page_config(**kwargs):
        calls.append(("set_page_config", kwargs))

    def tabs(labels):
        calls.append(("tabs", labels))
        return [_Tab(), _Tab()]

    def cache_data(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]

        def decorator(func):
            return func

        return decorator

    streamlit.set_page_config = set_page_config
    streamlit.tabs = tabs
    streamlit.cache_data = cache_data
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)


def test_app_and_worldcup_ui_import_without_statsmodels(monkeypatch):
    _block_statsmodels(monkeypatch)
    calls = []
    _install_streamlit_stub(monkeypatch, calls)

    sys.modules.pop("app", None)
    sys.modules.pop("worldcup.ui", None)
    ui = importlib.import_module("worldcup.ui")
    monkeypatch.setattr(ui, "render_worldcup_tab", lambda: calls.append(("render", "wc")))

    domestic_module = types.SimpleNamespace(
        render_domestic_leagues=lambda: calls.append(("render", "domestic"))
    )
    monkeypatch.setitem(sys.modules, "domestic.ui", domestic_module)

    importlib.import_module("app")

    assert ("tabs", ["World Cup 2026", "Big Five Leagues"]) in calls
    assert calls.index(("render", "wc")) < calls.index(("render", "domestic"))
    assert ("render", "domestic") in calls
    assert ("render", "wc") in calls


def test_available_models_predict_without_statsmodels(monkeypatch):
    _block_statsmodels(monkeypatch)
    from worldcup.model import ScorelineDist
    import worldcup.models as model_registry

    if not model_registry.STRENGTHS_PATH.exists():
        pytest.skip("pre-fitted World Cup strengths CSV is not committed")

    def missing_history():
        raise FileNotFoundError("history intentionally unavailable for smoke test")

    monkeypatch.setattr(model_registry, "load_history", missing_history)

    for name, factory in model_registry.AVAILABLE_MODELS.items():
        model = factory()
        dist = model.predict("United States", "Canada", neutral=True)
        assert isinstance(dist, ScorelineDist), name
        assert dist.grid.shape == (11, 11), name
        assert np.isclose(dist.grid.sum(), 1), name
        assert np.isfinite(dist.grid).all(), name
        assert ((0 <= dist.grid) & (dist.grid <= 1)).all(), name


def _tiny_worldcup_input():
    groups = {group: [f"{group}{idx}" for idx in range(1, 5)] for group in "AB"}
    groups_df = pd.DataFrame(
        [
            {
                "Group": group,
                "Team": team,
                "FIFA_Rank": group_idx * 4 + team_idx,
                "Confederation": "TEST",
            }
            for group_idx, (group, teams) in enumerate(groups.items())
            for team_idx, team in enumerate(teams, start=1)
        ]
    )
    rows = []
    match_id = 1
    for group, teams in groups.items():
        for i, home in enumerate(teams):
            for away in teams[i + 1 :]:
                rows.append(
                    {
                        "MatchID": match_id,
                        "Date": "2026-06-11",
                        "Stage": "Group",
                        "Group": group,
                        "HomeTeam": home,
                        "AwayTeam": away,
                        "Venue": "TBD",
                        "Neutral": True,
                    }
                )
                match_id += 1
    fixtures_df = pd.DataFrame(rows)
    results_df = pd.DataFrame(columns=["MatchID", "FTHG", "FTAG"])
    fifa_ranks = dict(zip(groups_df["Team"], groups_df["FIFA_Rank"]))
    return groups_df, fixtures_df, results_df, fifa_ranks


def _finite_values(value):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _finite_values(nested)
    elif isinstance(value, (int, float, np.integer, np.floating)):
        yield float(value)


def test_available_models_run_tiny_simulation_sanity_checks(tmp_path, monkeypatch):
    _block_statsmodels(monkeypatch)
    import worldcup.simulate as simulate_module
    from worldcup.model import EloModel
    import worldcup.models as model_registry
    from worldcup.simulate import simulate_tournament
    from worldcup.strengths import load_strengths

    if not model_registry.STRENGTHS_PATH.exists():
        pytest.skip("pre-fitted World Cup strengths CSV is not committed")

    def missing_history():
        raise FileNotFoundError("history intentionally unavailable for smoke test")

    monkeypatch.setattr(model_registry, "load_history", missing_history)
    monkeypatch.setattr(simulate_module, "CACHE_PATH", tmp_path / "wc_simulations.json")
    groups_df, fixtures_df, results_df, fifa_ranks = _tiny_worldcup_input()
    elo = {team: 1500 + 5 * (8 - rank) for team, rank in fifa_ranks.items()}
    strengths = load_strengths(model_registry.STRENGTHS_PATH)

    models = {}
    for name, factory in model_registry.AVAILABLE_MODELS.items():
        model = factory()
        if isinstance(model, EloModel):
            model.ratings = elo
        elif hasattr(model, "strengths"):
            model.strengths = strengths
        elif hasattr(model, "goal_strengths"):
            model.goal_strengths = strengths
        models[name] = model

    expected_keys = {
        "P(advance)",
        "P(win_group)",
        "P(top2_in_group)",
        "P(reach_R16)",
        "P(reach_QF)",
        "P(reach_SF)",
        "P(reach_Final)",
        "P(win_cup)",
        "xGF",
        "xGA",
        "finish_distribution",
    }
    probability_keys = {key for key in expected_keys if key.startswith("P(")}

    for name, model in models.items():
        result = simulate_tournament(
            model,
            groups_df,
            fixtures_df,
            results_df,
            fifa_ranks,
            n_sims=4,
            seed=2026,
            shootout="coin",
            elo=elo,
        )

        assert set(result["per_team"]) == set(groups_df["Team"]), name
        assert set(result["per_group"]) == {"A", "B"}, name
        for team_result in result["per_team"].values():
            assert set(team_result) == expected_keys
            for key in probability_keys:
                assert 0 <= team_result[key] <= 1
            finish_distribution = team_result["finish_distribution"]
            assert set(finish_distribution) == {"1st", "2nd", "3rd", "4th"}
            assert np.isclose(sum(finish_distribution.values()), 1)
        for value in _finite_values(result):
            assert math.isfinite(value), name


def test_worldcup_data_validate_passes():
    from worldcup.data import validate

    assert validate()["teams"] == 48
