import json
from pathlib import Path


DATA_ROOT = Path(__file__).resolve().parents[1] / "web" / "public" / "data"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_publishes_every_competition():
    manifest = _load(DATA_ROOT / "manifest.json")

    assert manifest["schemaVersion"] == "1.0.0"
    assert {entry["id"] for entry in manifest["leagues"]} == {
        "premier_league",
        "serie_a",
        "ligue_1",
        "la_liga",
        "bundesliga",
    }
    assert manifest["worldCup"]["id"] == "world-cup-2026"
    assert manifest["worldCup"]["status"] == "ready"


def test_domestic_artifacts_have_full_coverage_and_valid_match_probabilities():
    manifest = _load(DATA_ROOT / "manifest.json")

    for entry in manifest["leagues"]:
        artifact = _load(DATA_ROOT / Path(entry["dataUrl"]).name)
        assert artifact["kind"] == "domestic-league-forecast"
        assert artifact["isDemo"] is False
        assert artifact["coverage"]["teamsIncluded"] == entry["expectedTeams"]
        assert artifact["coverage"]["fixturesIncluded"] == artifact["coverage"]["fixturesExpected"]
        assert len(artifact["standings"]) == entry["expectedTeams"]
        forecasts = [fixture["forecast"] for fixture in artifact["fixtures"] if fixture["forecast"]]
        assert forecasts
        for forecast in forecasts:
            total = forecast["homeWin"] + forecast["draw"] + forecast["awayWin"]
            assert abs(total - 1.0) < 1e-8


def test_worldcup_artifact_has_groups_teams_and_bracket():
    artifact = _load(DATA_ROOT / "world-cup-2026.json")

    assert artifact["kind"] == "tournament-forecast"
    assert artifact["coverage"] == {
        "teamsIncluded": 48,
        "teamsExpected": 48,
        "groupsIncluded": 12,
        "groupsExpected": 12,
    }
    assert len(artifact["teams"]) == 48
    assert len(artifact["groups"]) == 12
    assert artifact["bracket"]
