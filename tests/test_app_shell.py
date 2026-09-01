import importlib
import sys
import types


class _Tab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_root_app_creates_domestic_and_worldcup_tabs(monkeypatch):
    calls = []
    streamlit = types.SimpleNamespace()

    def set_page_config(**kwargs):
        calls.append(("set_page_config", kwargs))

    def tabs(labels):
        calls.append(("tabs", labels))
        return [_Tab(), _Tab()]

    streamlit.set_page_config = set_page_config
    streamlit.tabs = tabs

    domestic_module = types.SimpleNamespace(
        render_domestic_leagues=lambda: calls.append(("render", "domestic"))
    )
    wc_module = types.SimpleNamespace(
        render_worldcup_tab=lambda: calls.append(("render", "wc"))
    )

    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setitem(sys.modules, "domestic.ui", domestic_module)
    monkeypatch.setitem(sys.modules, "worldcup.ui", wc_module)
    sys.modules.pop("app", None)

    importlib.import_module("app")

    assert calls[0][0] == "set_page_config"
    assert calls[0][1]["page_title"] == "MultiForecast — World Cup & Big Five Leagues"
    assert ("tabs", ["World Cup 2026", "Big Five Leagues"]) in calls
    assert calls.index(("render", "wc")) < calls.index(("render", "domestic"))
    assert ("render", "domestic") in calls
    assert ("render", "wc") in calls
