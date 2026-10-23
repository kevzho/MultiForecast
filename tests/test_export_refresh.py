import json
from types import SimpleNamespace

import pytest

import export_forecasts as exporter


@pytest.mark.parametrize("include_worldcup", [False, True])
def test_export_supports_live_refresh_and_full_export(tmp_path, monkeypatch, include_worldcup):
    previous = {"id": "world-cup-2026", "generatedAt": "previous"}
    (tmp_path / "manifest.json").write_text(json.dumps({"worldCup": previous}))
    (tmp_path / "world-cup-2026.json").write_text("existing tournament")
    monkeypatch.setattr(exporter, "build_forecast", lambda *a, **k: SimpleNamespace(generated_at="new"))
    monkeypatch.setattr(exporter, "build_league_artifact", lambda *a, **k: {"status": "ready"})
    calls = []

    def build_worldcup(**kwargs):
        calls.append(kwargs)
        return {"generatedAt": "new tournament"}

    monkeypatch.setattr(exporter, "build_worldcup_artifact", build_worldcup)
    manifest = exporter.export_forecasts(
        output_dir=tmp_path, leagues=["premier_league"],
        include_worldcup=include_worldcup, worldcup_simulations=10,
    )

    assert manifest["leagues"][0]["id"] == "premier_league"
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    if include_worldcup:
        assert calls == [{"n_simulations": 10}]
        assert manifest["worldCup"]["generatedAt"] == "new tournament"
        assert json.loads((tmp_path / "world-cup-2026.json").read_text())["generatedAt"] == "new tournament"
    else:
        assert calls == []
        assert manifest["worldCup"] == previous
        assert (tmp_path / "world-cup-2026.json").read_text() == "existing tournament"
