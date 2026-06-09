import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.bracket import THIRD_PLACE_TABLE_VERIFIED, advance, build_r32


def _group_results():
    return {
        group: {
            "winner": f"{group}1",
            "runner_up": f"{group}2",
            "third": f"{group}3",
        }
        for group in "ABCDEFGHIJKL"
    }


def test_build_r32_returns_16_pairings_and_32_unique_teams():
    best_thirds = ["A3", "C3", "E3", "F3", "H3", "I3", "J3", "K3"]

    pairings = build_r32(_group_results(), best_thirds)
    teams = [team for pairing in pairings for team in pairing]

    assert THIRD_PLACE_TABLE_VERIFIED is True
    assert len(pairings) == 16
    assert len(teams) == 32
    assert len(set(teams)) == 32


def test_full_progression_to_one_champion_with_deterministic_winner_fn():
    r32 = build_r32(_group_results(), ["A3", "C3", "E3", "F3", "H3", "I3", "J3", "K3"])

    def winner_fn(team_a, team_b):
        return min(team_a, team_b), max(team_a, team_b)

    r16, _ = advance(r32, winner_fn)
    qf, _ = advance(r16, winner_fn)
    sf, _ = advance(qf, winner_fn)
    final, third_place = advance(sf, winner_fn)
    champion_pairing, final_loser = advance(final, winner_fn)

    champion = champion_pairing[0][0]

    assert len(r16) == 8
    assert len(qf) == 4
    assert len(sf) == 2
    assert len(final) == 1
    assert len(third_place) == 1
    assert len(third_place[0]) == 2
    assert final_loser[0] not in champion_pairing[0]
    assert len(champion_pairing) == 1
    assert champion == min(team for pairing in r32 for team in pairing)
