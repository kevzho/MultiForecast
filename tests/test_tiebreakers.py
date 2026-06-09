import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.tiebreakers import rank_group, rank_third_place


def test_rank_group_clean_no_tie():
    matches = [
        {"group": "A", "home": "Alpha", "away": "Bravo", "hg": 2, "ag": 0},
        {"group": "A", "home": "Alpha", "away": "Charlie", "hg": 1, "ag": 0},
        {"group": "A", "home": "Alpha", "away": "Delta", "hg": 3, "ag": 1},
        {"group": "A", "home": "Bravo", "away": "Charlie", "hg": 2, "ag": 0},
        {"group": "A", "home": "Bravo", "away": "Delta", "hg": 1, "ag": 0},
        {"group": "A", "home": "Charlie", "away": "Delta", "hg": 2, "ag": 0},
    ]

    ordered, stats = rank_group(matches, {"Alpha": 10, "Bravo": 20, "Charlie": 30, "Delta": 40})

    assert ordered == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert stats["Alpha"]["pts"] == 9
    assert stats["Alpha"]["gd"] == 5
    assert stats["Alpha"]["gf"] == 6
    assert stats["Alpha"]["group"] == "A"


def test_two_team_tie_drawn_h2h_broken_by_fifa_rank():
    matches = [
        {"group": "B", "home": "Alpha", "away": "Bravo", "hg": 1, "ag": 1},
        {"group": "B", "home": "Alpha", "away": "Charlie", "hg": 2, "ag": 0},
        {"group": "B", "home": "Alpha", "away": "Delta", "hg": 1, "ag": 0},
        {"group": "B", "home": "Bravo", "away": "Charlie", "hg": 2, "ag": 0},
        {"group": "B", "home": "Bravo", "away": "Delta", "hg": 1, "ag": 0},
        {"group": "B", "home": "Charlie", "away": "Delta", "hg": 1, "ag": 0},
    ]

    ordered, _ = rank_group(matches, {"Alpha": 5, "Bravo": 25, "Charlie": 35, "Delta": 45})

    assert ordered[:2] == ["Alpha", "Bravo"]


def test_three_way_tie_broken_by_among_tied_subset():
    matches = [
        {"group": "C", "home": "Alpha", "away": "Bravo", "hg": 2, "ag": 0},
        {"group": "C", "home": "Bravo", "away": "Charlie", "hg": 1, "ag": 0},
        {"group": "C", "home": "Charlie", "away": "Alpha", "hg": 1, "ag": 0},
        {"group": "C", "home": "Alpha", "away": "Delta", "hg": 2, "ag": 1},
        {"group": "C", "home": "Bravo", "away": "Delta", "hg": 3, "ag": 0},
        {"group": "C", "home": "Charlie", "away": "Delta", "hg": 3, "ag": 1},
    ]

    ordered, _ = rank_group(matches, {"Alpha": 30, "Bravo": 10, "Charlie": 20, "Delta": 40})

    assert ordered[:3] == ["Alpha", "Charlie", "Bravo"]


def test_rank_third_place_picks_top_8_with_mixed_records():
    thirds = [
        {"team": "A3", "group": "A", "pts": 6, "gd": 1, "gf": 4},
        {"team": "B3", "group": "B", "pts": 4, "gd": 2, "gf": 5},
        {"team": "C3", "group": "C", "pts": 4, "gd": 2, "gf": 4},
        {"team": "D3", "group": "D", "pts": 4, "gd": 0, "gf": 6},
        {"team": "E3", "group": "E", "pts": 4, "gd": 0, "gf": 5},
        {"team": "F3", "group": "F", "pts": 3, "gd": 1, "gf": 3},
        {"team": "G3", "group": "G", "pts": 3, "gd": 0, "gf": 5},
        {"team": "H3", "group": "H", "pts": 3, "gd": 0, "gf": 4, "fair_play": -1},
        {"team": "I3", "group": "I", "pts": 3, "gd": 0, "gf": 4, "fair_play": -3},
        {"team": "J3", "group": "J", "pts": 2, "gd": 3, "gf": 8},
        {"team": "K3", "group": "K", "pts": 1, "gd": 0, "gf": 2},
        {"team": "L3", "group": "L", "pts": 0, "gd": 0, "gf": 1},
    ]
    fifa_ranks = {third["team"]: idx for idx, third in enumerate(thirds, start=1)}

    top8, full = rank_third_place(thirds, fifa_ranks)

    assert top8 == ["A3", "B3", "C3", "D3", "E3", "F3", "G3", "H3"]
    assert full[:9] == ["A3", "B3", "C3", "D3", "E3", "F3", "G3", "H3", "I3"]
