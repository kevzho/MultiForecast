import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.data import load_fixtures, load_groups, validate


def test_validate_passes():
    summary = validate()

    assert summary["teams"] == 48
    assert summary["groups"] == 12
    assert summary["group_fixtures"] == 72


def test_group_and_fixture_counts():
    groups = load_groups()
    fixtures = load_fixtures()

    assert groups["Team"].nunique() == 48
    assert groups["Group"].nunique() == 12
    assert len(fixtures[fixtures["Stage"] == "Group"]) == 72
