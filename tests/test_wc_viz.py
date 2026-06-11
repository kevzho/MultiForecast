import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.viz import most_likely_bracket


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
    for round_name, matchups in bracket["rounds"].items():
        assert matchups, round_name
        for matchup in matchups:
            assert set(matchup) == {
                "team_a",
                "team_b",
                "winner",
                "p_advance_winner",
            }
            assert matchup["winner"] in {matchup["team_a"], matchup["team_b"]}
            assert 0 <= matchup["p_advance_winner"] <= 1
            assert math.isfinite(matchup["p_advance_winner"])
