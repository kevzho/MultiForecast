import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.viz import all_team_probabilities, most_likely_bracket


def _simulation_stub():
    per_team = {}
    per_group = {}
    rank = 48
    for group in "ABCDEFGHIJKL":
        per_group[group] = {}
        for idx in range(1, 5):
            team = f"{group}{idx}"
            strength = rank / 48
            stats = {
                "P(advance)": min(1.0, 0.2 + strength * 0.7),
                "P(win_group)": min(1.0, 0.1 + strength * 0.6),
                "P(top2_in_group)": min(1.0, 0.2 + strength * 0.65),
                "P(reach_R16)": min(1.0, 0.1 + strength * 0.55),
                "P(reach_QF)": min(1.0, 0.08 + strength * 0.45),
                "P(reach_SF)": min(1.0, 0.05 + strength * 0.35),
                "P(reach_Final)": min(1.0, 0.03 + strength * 0.25),
                "P(win_cup)": min(1.0, 0.01 + strength * 0.18),
                "finish_distribution": {
                    "1st": min(1.0, 0.1 + strength * 0.6),
                    "2nd": 0.2,
                    "3rd": 0.2,
                    "4th": max(0.0, 0.5 - strength * 0.6),
                },
            }
            total_finish = sum(stats["finish_distribution"].values())
            stats["finish_distribution"] = {
                key: value / total_finish
                for key, value in stats["finish_distribution"].items()
            }
            per_team[team] = stats
            per_group[group][team] = stats["finish_distribution"]
            rank -= 1
    return {"per_team": per_team, "per_group": per_group}


def test_most_likely_bracket_exposes_pairing_outcomes():
    bracket = most_likely_bracket(_simulation_stub())

    assert bracket["champion"]
    for matchup in _all_matchups(bracket):
        _assert_valid_matchup(matchup)


def test_most_likely_bracket_splits_halves_and_center_final():
    bracket = most_likely_bracket(_simulation_stub())
    rounds = bracket["rounds"]

    assert set(rounds) == {"left", "right", "Final"}
    for side in ("left", "right"):
        assert [len(rounds[side][round_name]) for round_name in ("R32", "R16", "QF", "SF")] == [
            8,
            4,
            2,
            1,
        ]
    assert len(rounds["Final"]) == 1
    for matchup in _all_matchups(bracket):
        _assert_valid_matchup(matchup)


def test_all_team_probabilities_has_every_team_sorted_and_valid():
    simulation = _simulation_stub()
    rows = all_team_probabilities(simulation)

    assert len(rows) == len(simulation["per_team"])
    assert {row["Team"] for row in rows} == set(simulation["per_team"])
    assert [row["P(win_cup)"] for row in rows] == sorted(
        [row["P(win_cup)"] for row in rows],
        reverse=True,
    )
    for row in rows:
        assert set(row) == {
            "Team",
            "Group",
            "P(advance)",
            "P(reach_QF)",
            "P(reach_SF)",
            "P(reach_Final)",
            "P(win_cup)",
        }
        for key, value in row.items():
            if key.startswith("P("):
                assert 0 <= value <= 1
                assert math.isfinite(value)


def _all_matchups(bracket: dict) -> list[dict]:
    rounds = bracket["rounds"]
    matchups = []
    for side in ("left", "right"):
        for round_name in ("R32", "R16", "QF", "SF"):
            matchups.extend(rounds[side][round_name])
    matchups.extend(rounds["Final"])
    return matchups


def _assert_valid_matchup(matchup: dict) -> None:
    assert set(matchup) == {
        "team_a",
        "team_b",
        "winner",
        "p_advance_winner",
    }
    assert matchup["winner"] in {matchup["team_a"], matchup["team_b"]}
    assert 0 <= matchup["p_advance_winner"] <= 1
    assert math.isfinite(matchup["p_advance_winner"])
