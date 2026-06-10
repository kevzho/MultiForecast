from typing import Dict, Any, List, Tuple
from collections import OrderedDict
from .team_names import normalize_intl_team


def _pct_whole(x: float) -> str:
    return f"{round(x*100):d}%"


def _round_table(x: float) -> float:
    # one decimal in tables represented as 0-1 floats to one decimal when rendered
    return round(x, 3)


def group_stage_narrative(result: Dict[str, Any], group: str) -> str:
    """Return a short paragraph summarizing the state of `group`.

    Uses `result` produced by `simulate_tournament` (see contract in task).
    """
    per_group = result.get("per_group", {})
    per_team = result.get("per_team", {})
    grp = per_group.get(group)
    if not grp:
        return f"Group {group}: no simulation data available."

    # teams is mapping team->finish_distribution
    teams = list(grp.keys())
    # favourite: highest P(win_group)
    fav = None
    fav_p = -1.0
    for t in teams:
        p = per_team.get(t, {}).get("P(win_group)", 0.0)
        if p > fav_p:
            fav_p = p
            fav = t

    # likely second qualifier: by P(top2_in_group) or P(advance)
    second = None
    second_p = -1.0
    for t in teams:
        p = per_team.get(t, {}).get("P(top2_in_group)", per_team.get(t, {}).get("P(advance)", 0.0))
        if t != fav and p > second_p:
            second_p = p
            second = t

    # dark horse: smallest win_group but meaningful advance prob
    dark = None
    dark_p = 0.0
    for t in teams:
        if t in (fav, second):
            continue
        p_adv = per_team.get(t, {}).get("P(advance)", 0.0)
        # meaningful = at least 10%
        if p_adv >= 0.10 and p_adv > dark_p:
            dark_p = p_adv
            dark = t
    if dark is None:
        # pick the next-best by advance prob
        cand = [(t, per_team.get(t, {}).get("P(advance)", 0.0)) for t in teams if t not in (fav, second)]
        cand.sort(key=lambda x: x[1], reverse=True)
        if cand:
            dark, dark_p = cand[0]

    # most likely eliminated: lowest P(advance)
    elim = min(teams, key=lambda t: per_team.get(t, {}).get("P(advance)", 0.0))
    elim_p = per_team.get(elim, {}).get("P(advance)", 0.0)

    fav_name = normalize_intl_team(fav) if fav else "(unknown)"
    second_name = normalize_intl_team(second) if second else "(unknown)"
    dark_name = normalize_intl_team(dark) if dark else "(none)"
    elim_name = normalize_intl_team(elim)

    parts = []
    parts.append(f"Group {group}: {fav_name} are heavy favorites to top Group {group} ({_pct_whole(fav_p)}),")
    parts.append(f" with {second_name} most likely to join them ({_pct_whole(second_p)}).")
    if dark and dark_p > 0:
        parts.append(f" {dark_name} are a dark horse with {_pct_whole(dark_p)} chance to advance.")
    parts.append(f" {elim_name} are most likely to be eliminated ({_pct_whole(1-elim_p)} chance to not advance).")

    return "".join(parts)


def qualification_table(result: Dict[str, Any], group: str) -> List[Dict[str, Any]]:
    """Return rows sorted by P(advance) desc: {team, p_advance, p_win_group, most_likely_finish}.
    p_advance and p_win_group are floats (0..1) rounded to 3 decimals for table display.
    """
    per_group = result.get("per_group", {})
    per_team = result.get("per_team", {})
    grp = per_group.get(group, {})
    rows: List[Dict[str, Any]] = []
    for team in grp.keys():
        tstats = per_team.get(team, {})
        p_adv = _round_table(tstats.get("P(advance)", 0.0))
        p_win = _round_table(tstats.get("P(win_group)", 0.0))
        finish_dist = tstats.get("finish_distribution", {})
        most_likely_finish = None
        if finish_dist:
            # keys like '1st','2nd'
            most_likely_finish = max(finish_dist.items(), key=lambda x: x[1])[0]
        rows.append({"team": team, "p_advance": p_adv, "p_win_group": p_win, "most_likely_finish": most_likely_finish})

    rows.sort(key=lambda r: r["p_advance"], reverse=True)
    return rows


def title_contenders(result: Dict[str, Any], top_n: int = 8) -> List[Dict[str, Any]]:
    """Return top teams by P(win_cup): {team, p_win_cup, p_reach_final, p_reach_sf}.
    p values are floats in [0,1], rounded to 3 decimals for table display.
    """
    per_team = result.get("per_team", {})
    rows: List[Dict[str, Any]] = []
    for team, stats in per_team.items():
        p_win = stats.get("P(win_cup)", 0.0)
        p_final = stats.get("P(reach_Final)", 0.0)
        p_sf = stats.get("P(reach_SF)", 0.0)
        rows.append({"team": team, "p_win_cup": _round_table(p_win), "p_reach_final": _round_table(p_final), "p_reach_sf": _round_table(p_sf)})

    rows.sort(key=lambda r: r["p_win_cup"], reverse=True)
    return rows[:top_n]


def overperformers_underperformers(result: Dict[str, Any], fifa_ranks: Dict[str, int]) -> Dict[str, List[Dict[str, str]]]:
    """Compare each team's P(reach_QF) vs a linear expectation from FIFA rank.

    `fifa_ranks` maps team -> rank (1 best). Returns dict with keys
    'overperformers' and 'underperformers', each a list of {team, reason}.
    """
    per_team = result.get("per_team", {})
    # prepare ranks: lower rank = better
    # normalize expectation: expected_p = 1 - (rank-1)/(max_rank-1)
    ranks = {t: fifa_ranks.get(t) for t in per_team.keys()}
    valid_ranks = [r for r in ranks.values() if isinstance(r, int)]
    if not valid_ranks:
        # no ranks available: return empty lists
        return {"overperformers": [], "underperformers": []}
    max_rank = max(valid_ranks)

    over = []
    under = []
    for team, stats in per_team.items():
        rank = fifa_ranks.get(team)
        p_qf = stats.get("P(reach_QF)", 0.0)
        if rank is None:
            continue
        expected = 1.0 - (rank - 1) / max(1, (max_rank - 1))
        diff = p_qf - expected
        # threshold 5 percentage points
        if diff >= 0.05:
            reason = f"P(reach_QF)={round(p_qf*100,1)}% vs expectation {round(expected*100,1)}% (+{round(diff*100,1)}%)"
            over.append({"team": team, "reason": reason})
        elif diff <= -0.05:
            reason = f"P(reach_QF)={round(p_qf*100,1)}% vs expectation {round(expected*100,1)}% ({round(diff*100,1)}%)"
            under.append({"team": team, "reason": reason})

    return {"overperformers": over, "underperformers": under}


def headline(result: Dict[str, Any]) -> str:
    per_team = result.get("per_team", {})
    if not per_team:
        return "No simulation results available."

    fav = max(per_team.items(), key=lambda kv: kv[1].get("P(win_cup)", 0.0))[0]
    fav_p = per_team[fav].get("P(win_cup)", 0.0)

    # pick a surprise: team with P(reach_QF) >= 0.15 but low win prob
    surprises = [(t, s.get("P(reach_QF)", 0.0)) for t, s in per_team.items() if s.get("P(win_cup)", 0.0) < 0.05]
    surprise = None
    if surprises:
        surprise = max(surprises, key=lambda x: x[1])[0]

    fav_name = normalize_intl_team(fav)
    if surprise:
        return f"{fav_name} are favourites ({round(fav_p*100)}%), while {normalize_intl_team(surprise)} are an intriguing surprise."
    return f"{fav_name} are favourites ({round(fav_p*100)}%)."
