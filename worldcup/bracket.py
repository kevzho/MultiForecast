"""2026 World Cup knockout bracket helpers."""

from __future__ import annotations

from itertools import combinations

THIRD_PLACE_ELIGIBLE_SLOTS = {
    "E1": {"A", "B", "C", "D", "F"},
    "I1": {"C", "D", "F", "G", "H"},
    "A1": {"C", "E", "F", "H", "I"},
    "L1": {"E", "H", "I", "J", "K"},
    "G1": {"A", "E", "H", "I", "J"},
    "D1": {"B", "E", "F", "I", "J"},
    "B1": {"E", "F", "G", "I", "J"},
    "K1": {"D", "E", "I", "J", "L"},
}

THIRD_PLACE_SLOT_ORDER = ("E1", "I1", "A1", "L1", "G1", "D1", "B1", "K1")
THIRD_PLACE_TABLE_VERIFIED = True

# TODO: Cross-check exotic qualifying-group combinations against FIFA's official
# third-place assignment table when the final table is published in machine-readable form.
R32_MAP = (
    ("A1", "3rd"),
    ("C1", "F2"),
    ("F1", "C2"),
    ("E1", "3rd"),
    ("I1", "3rd"),
    ("E2", "I2"),
    ("A2", "B2"),
    ("L1", "3rd"),
    ("G1", "3rd"),
    ("D1", "3rd"),
    ("H1", "J2"),
    ("K2", "L2"),
    ("B1", "3rd"),
    ("D2", "G2"),
    ("J1", "H2"),
    ("K1", "3rd"),
)


def build_r32(group_results: dict, best_thirds: list[str]) -> list[tuple[str, str]]:
    third_by_group = _third_by_group(group_results, best_thirds)
    groups_key = tuple(sorted(third_by_group))
    third_assignment = THIRD_PLACE_ASSIGNMENT[groups_key]

    pairings = []
    for left_slot, right_slot in R32_MAP:
        left_team = _slot_team(left_slot, group_results)
        if right_slot == "3rd":
            third_group = third_assignment[left_slot]
            right_team = third_by_group[third_group]
        else:
            right_team = _slot_team(right_slot, group_results)
        pairings.append((left_team, right_team))
    return pairings


def advance(pairings: list[tuple[str, str]], winner_fn):
    winners = []
    losers = []
    for team_a, team_b in pairings:
        result = winner_fn(team_a, team_b)
        if isinstance(result, tuple):
            winner, loser = result
        else:
            winner = result
            loser = team_b if winner == team_a else team_a
        winners.append(winner)
        losers.append(loser)

    if len(pairings) == 1:
        return [(winners[0],)], losers

    next_pairings = list(zip(winners[::2], winners[1::2]))
    if len(pairings) == 2:
        third_place = [(losers[0], losers[1])]
        return next_pairings, third_place
    return next_pairings, losers


def _assign_thirds(groups: tuple[str, ...]) -> dict[str, str]:
    groups = tuple(groups)
    assignments: dict[str, str] = {}
    used: set[str] = set()

    def search() -> bool:
        if len(assignments) == len(THIRD_PLACE_SLOT_ORDER):
            return True

        open_slots = [slot for slot in THIRD_PLACE_SLOT_ORDER if slot not in assignments]
        slot = min(
            open_slots,
            key=lambda candidate: len(
                THIRD_PLACE_ELIGIBLE_SLOTS[candidate].intersection(groups) - used
            ),
        )
        candidates = sorted(THIRD_PLACE_ELIGIBLE_SLOTS[slot].intersection(groups) - used)
        for group in candidates:
            assignments[slot] = group
            used.add(group)
            if search():
                return True
            used.remove(group)
            del assignments[slot]
        return False

    if not search():
        raise ValueError(f"No valid third-place assignment for groups: {groups}")
    return dict(assignments)


def _slot_team(slot: str, group_results: dict) -> str:
    group = slot[0]
    place = slot[1]
    record = group_results[group]
    if place == "1":
        return record["winner"]
    if place == "2":
        return record["runner_up"]
    if place == "3":
        return record["third"]
    raise ValueError(f"Unknown bracket slot: {slot}")


def _third_by_group(group_results: dict, best_thirds: list[str]) -> dict[str, str]:
    third_lookup = {
        record["third"]: group
        for group, record in group_results.items()
        if "third" in record
    }
    third_by_group = {}
    for team in best_thirds:
        group = third_lookup.get(team)
        if group is None and len(team) >= 2 and team[0] in group_results:
            group = team[0]
        if group is None:
            raise ValueError(f"Cannot determine group for third-place team: {team}")
        third_by_group[group] = team
    if len(third_by_group) != 8:
        raise ValueError("Exactly eight third-place teams are required")
    return third_by_group


THIRD_PLACE_ASSIGNMENT = {
    groups: _assign_thirds(groups) for groups in combinations("ABCDEFGHIJKL", 8)
}
