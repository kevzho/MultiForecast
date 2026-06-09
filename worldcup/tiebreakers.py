"""FIFA-style group and third-place ranking rules for World Cup 2026."""

from __future__ import annotations

from itertools import combinations
from math import inf
from typing import Iterable


def rank_group(
    matches: list[dict],
    fifa_ranks: dict[str, int],
    fair_play: dict[str, int] | None = None,
) -> tuple[list[str], dict[str, dict]]:
    """Rank a four-team group using FIFA criteria in order."""
    fair_play = fair_play or {}
    teams = _teams_from_matches(matches)
    group_label = _group_label(matches)
    stats = _stats_for_matches(teams, matches, group_label=group_label, fair_play=fair_play)

    ordered = []
    for cluster in _clusters_by_key(teams, lambda team: _overall_key(stats[team])):
        if len(cluster) == 1:
            ordered.extend(cluster)
        else:
            ordered.extend(_break_h2h_cluster(cluster, matches, fifa_ranks, fair_play))

    return ordered, stats


def rank_third_place(
    thirds_stats,
    fifa_ranks: dict[str, int],
    fair_play: dict[str, int] | None = None,
) -> tuple[list[str], list[str]]:
    """Rank group-third teams and return the top eight plus the full ordering."""
    fair_play = fair_play or {}
    records = _third_records(thirds_stats)

    def key(record: dict) -> tuple:
        team = record["team"]
        return (
            -record.get("pts", 0),
            -record.get("gd", 0),
            -record.get("gf", 0),
            -record.get("fair_play", fair_play.get(team, 0)),
            fifa_ranks.get(team, inf),
            team,
        )

    ordered_records = sorted(records, key=key)
    full_ranking = [record["team"] for record in ordered_records]
    return full_ranking[:8], full_ranking


def _teams_from_matches(matches: Iterable[dict]) -> list[str]:
    teams = []
    for match in matches:
        for key in ("home", "away"):
            team = match[key]
            if team not in teams:
                teams.append(team)
    return teams


def _group_label(matches: list[dict]) -> str | None:
    for match in matches:
        if "group" in match:
            return match["group"]
    return None


def _stats_for_matches(
    teams: list[str],
    matches: list[dict],
    *,
    group_label: str | None = None,
    fair_play: dict[str, int] | None = None,
) -> dict[str, dict]:
    fair_play = fair_play or {}
    stats = {
        team: {
            "team": team,
            "pts": 0,
            "gd": 0,
            "gf": 0,
            "ga": 0,
            "group": group_label,
            "fair_play": fair_play.get(team, 0),
        }
        for team in teams
    }

    for match in matches:
        home = match["home"]
        away = match["away"]
        hg = int(match["hg"])
        ag = int(match["ag"])

        stats[home]["gf"] += hg
        stats[home]["ga"] += ag
        stats[away]["gf"] += ag
        stats[away]["ga"] += hg

        if hg > ag:
            stats[home]["pts"] += 3
        elif hg < ag:
            stats[away]["pts"] += 3
        else:
            stats[home]["pts"] += 1
            stats[away]["pts"] += 1

    for team_stats in stats.values():
        team_stats["gd"] = team_stats["gf"] - team_stats["ga"]

    return stats


def _overall_key(stats: dict) -> tuple[int, int, int]:
    return stats["pts"], stats["gd"], stats["gf"]


def _h2h_key(stats: dict) -> tuple[int, int, int]:
    return stats["pts"], stats["gd"], stats["gf"]


def _fallback_key(team: str, fifa_ranks: dict[str, int], fair_play: dict[str, int]) -> tuple:
    return (-fair_play.get(team, 0), fifa_ranks.get(team, inf), team)


def _clusters_by_key(teams: list[str], key_fn) -> list[list[str]]:
    ordered = sorted(teams, key=lambda team: key_fn(team), reverse=True)
    clusters = []
    for team in ordered:
        if not clusters or key_fn(team) != key_fn(clusters[-1][0]):
            clusters.append([team])
        else:
            clusters[-1].append(team)
    return clusters


def _break_h2h_cluster(
    teams: list[str],
    matches: list[dict],
    fifa_ranks: dict[str, int],
    fair_play: dict[str, int],
) -> list[str]:
    h2h_matches = [
        match
        for match in matches
        if match["home"] in teams and match["away"] in teams
    ]
    h2h_stats = _stats_for_matches(teams, h2h_matches, fair_play=fair_play)
    clusters = _clusters_by_key(teams, lambda team: _h2h_key(h2h_stats[team]))

    ordered = []
    for cluster in clusters:
        if len(cluster) == 1:
            ordered.extend(cluster)
        elif len(cluster) < len(teams):
            ordered.extend(_break_h2h_cluster(cluster, matches, fifa_ranks, fair_play))
        else:
            ordered.extend(
                sorted(
                    cluster,
                    key=lambda team: _fallback_key(team, fifa_ranks, fair_play),
                )
            )
    return ordered


def _third_records(thirds_stats) -> list[dict]:
    if isinstance(thirds_stats, dict):
        records = []
        for team, stats in thirds_stats.items():
            record = {"team": team, **stats}
            records.append(record)
        return records
    return [dict(record) for record in thirds_stats]
