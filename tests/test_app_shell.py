import importlib
import sys
import types


class _Tab:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_root_app_creates_pl_and_worldcup_tabs(monkeypatch):
    calls = []
    streamlit = types.SimpleNamespace()

    def set_page_config(**kwargs):
        calls.append(("set_page_config", kwargs))

    def tabs(labels):
        calls.append(("tabs", labels))
        return [_Tab(), _Tab()]

    streamlit.set_page_config = set_page_config
    streamlit.tabs = tabs

    pl_module = types.SimpleNamespace(
        render_premier_league=lambda: calls.append(("render", "pl"))
    )
    wc_module = types.SimpleNamespace(
        render_worldcup_tab=lambda: calls.append(("render", "wc"))
    )

    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setitem(sys.modules, "premier_league.dashboard", pl_module)
    monkeypatch.setitem(sys.modules, "worldcup.ui", wc_module)
    sys.modules.pop("app", None)

    importlib.import_module("app")

    assert ("tabs", ["Premier League", "World Cup 2026"]) in calls
    assert ("render", "pl") in calls
    assert ("render", "wc") in calls
