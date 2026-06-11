"""Projection-table builders for the World Cup Streamlit UI."""

from __future__ import annotations

from worldcup.bracket import build_r32
from worldcup.insights import group_stage_narrative, headline

ROUND_NEXT_PROB = {
    "R32": "P(reach_R16)",
    "R16": "P(reach_QF)",
    "QF": "P(reach_SF)",
    "SF": "P(reach_Final)",
    "Final": "P(win_cup)",
}


def favorite_metric(simulation: dict) -> dict:
    per_team = simulation.get("per_team", {})
    if not per_team:
        return {"team": "", "p_win_cup": 0.0, "headline": headline(simulation)}
    team, stats = max(per_team.items(), key=lambda item: item[1].get("P(win_cup)", 0.0))
    return {
        "team": team,
        "p_win_cup": stats.get("P(win_cup)", 0.0),
        "headline": headline(simulation),
    }


def projected_group_standings(simulation: dict, group: str) -> list[dict]:
    per_group = simulation.get("per_group", {}).get(group, {})
    per_team = simulation.get("per_team", {})
    rows = []
    ordered = sorted(
        per_group,
        key=lambda team: (
            per_team.get(team, {}).get("P(advance)", 0.0),
            per_team.get(team, {}).get("P(top2_in_group)", 0.0),
            -_expected_finish(per_team.get(team, {}).get("finish_distribution", {})),
        ),
        reverse=True,
    )
    for idx, team in enumerate(ordered, start=1):
        stats = per_team.get(team, {})
        tag = ""
        if idx <= 2:
            tag = "QUALIFIES"
        elif idx == 3:
            tag = "possible best-3rd"
        rows.append(
            {
                "Group": group,
                "Team": team,
                "Projected Rank": idx,
                "Tag": tag,
                "P(advance)": stats.get("P(advance)", 0.0),
                "P(win_group)": stats.get("P(win_group)", 0.0),
                "P(top2_in_group)": stats.get("P(top2_in_group)", 0.0),
                "Projected Finish": most_likely_finish(stats),
            }
        )
    return rows


def finish_distribution_rows(simulation: dict, group: str) -> list[dict]:
    rows = []
    per_group = simulation.get("per_group", {}).get(group, {})
    per_team = simulation.get("per_team", {})
    for team in per_group:
        finish_distribution = per_team.get(team, {}).get("finish_distribution", {})
        for finish in ("1st", "2nd", "3rd", "4th"):
            rows.append(
                {
                    "Team": team,
                    "Finish": finish,
                    "Probability": finish_distribution.get(finish, 0.0),
                }
            )
    return rows


def group_projection(simulation: dict, group: str) -> dict:
    return {
        "narrative": group_stage_narrative(simulation, group),
        "standings": projected_group_standings(simulation, group),
        "finish_distribution": finish_distribution_rows(simulation, group),
    }


def group_exit_table(simulation: dict) -> list[dict]:
    rows = []
    for group in sorted(simulation.get("per_group", {})):
        for row in projected_group_standings(simulation, group):
            rows.append(
                {
                    "Group": group,
                    "Team": row["Team"],
                    "P(advance)": row["P(advance)"],
                    "Projected Finish": row["Projected Finish"],
                }
            )
    return rows


def most_likely_bracket(simulation: dict) -> dict:
    group_results = _projected_group_results(simulation)
    if len(group_results) < 12:
        return _mini_bracket(simulation, group_results)
    best_thirds = _projected_best_thirds(simulation, group_results)
    rounds = {}
    pairings = build_r32(group_results, best_thirds)
    for round_name in ("R32", "R16", "QF", "SF", "Final"):
        rounds[round_name] = _advance_round(simulation, pairings, round_name)
        pairings = _next_round_pairings(rounds[round_name])
    champion = rounds["Final"][0]["winner"] if rounds.get("Final") else ""
    return {"rounds": rounds, "champion": champion}


def most_likely_finish(stats: dict) -> str:
    finish_distribution = stats.get("finish_distribution", {})
    if not finish_distribution:
        return ""
    return max(finish_distribution.items(), key=lambda item: item[1])[0]


def _projected_group_results(simulation: dict) -> dict:
    results = {}
    for group in sorted(simulation.get("per_group", {})):
        standings = projected_group_standings(simulation, group)
        if len(standings) >= 3:
            results[group] = {
                "winner": standings[0]["Team"],
                "runner_up": standings[1]["Team"],
                "third": standings[2]["Team"],
            }
    return results


def _projected_best_thirds(simulation: dict, group_results: dict) -> list[str]:
    per_team = simulation.get("per_team", {})
    thirds = [record["third"] for record in group_results.values()]
    thirds.sort(key=lambda team: per_team.get(team, {}).get("P(advance)", 0.0), reverse=True)
    return thirds[:8]


def _advance_round(simulation: dict, pairings: list[tuple[str, str]], round_name: str) -> list[dict]:
    return [_pairing_outcome(simulation, pairing, round_name) for pairing in pairings]


def _advance_pairing(simulation: dict, pairing: tuple[str, str], round_name: str) -> str:
    return _pairing_outcome(simulation, pairing, round_name)["winner"]


def _pairing_outcome(simulation: dict, pairing: tuple[str, str], round_name: str) -> dict:
    key = ROUND_NEXT_PROB[round_name]
    per_team = simulation.get("per_team", {})
    team_a, team_b = pairing
    prob_a = per_team.get(team_a, {}).get(key, 0.0)
    prob_b = per_team.get(team_b, {}).get(key, 0.0)
    if prob_a == prob_b:
        prob_a = per_team.get(team_a, {}).get("P(win_cup)", 0.0)
        prob_b = per_team.get(team_b, {}).get("P(win_cup)", 0.0)
    winner = team_a if prob_a >= prob_b else team_b
    return {
        "team_a": team_a,
        "team_b": team_b,
        "winner": winner,
        "p_advance_winner": per_team.get(winner, {}).get(key, 0.0),
    }


def _next_round_pairings(round_matchups: list[dict]) -> list[tuple[str, str]]:
    winners = [matchup["winner"] for matchup in round_matchups]
    return list(zip(winners[::2], winners[1::2]))


def _expected_finish(finish_distribution: dict) -> float:
    weights = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
    if not finish_distribution:
        return 99.0
    return sum(weights[key] * finish_distribution.get(key, 0.0) for key in weights)


def _mini_bracket(simulation: dict, group_results: dict) -> dict:
    groups = sorted(group_results)
    if len(groups) < 2:
        return {"rounds": {}, "champion": ""}
    pairings = [
        (group_results[groups[0]]["winner"], group_results[groups[1]]["runner_up"]),
        (group_results[groups[1]]["winner"], group_results[groups[0]]["runner_up"]),
    ]
    r32 = _advance_round(simulation, pairings, "R32")
    final_pairings = _next_round_pairings(r32)
    final = _advance_round(simulation, final_pairings, "Final")
    champion = final[0]["winner"] if final else ""
    return {"rounds": {"R32": r32, "Final": final}, "champion": champion}
