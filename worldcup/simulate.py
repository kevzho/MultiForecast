"""Monte Carlo tournament simulator for the 2026 World Cup data layer."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from worldcup.bracket import advance, build_r32
from worldcup.data import load_elo, load_fixtures, load_groups, load_results
from worldcup.model import EloModel, make_rng
from worldcup.tiebreakers import rank_group, rank_third_place

CACHE_PATH = Path(__file__).resolve().parents[1] / "cache" / "wc_simulations.json"
SHOOTOUT_ELO_K = 0.0007


def simulate_tournament(
    model,
    groups_df: pd.DataFrame,
    fixtures_df: pd.DataFrame,
    results_df: pd.DataFrame,
    fifa_ranks: dict[str, int],
    n_sims: int = 20000,
    seed: int = 42,
    shootout: str = "elo",
    elo: dict[str, float] | None = None,
) -> dict:
    cache_key = _cache_key(model, n_sims, results_df)
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    rng = make_rng(seed)
    elo = elo or getattr(model, "ratings", {})
    teams = list(groups_df["Team"])
    groups = {
        group: list(group_df["Team"])
        for group, group_df in groups_df.groupby("Group", sort=True)
    }
    group_fixtures = fixtures_df[fixtures_df["Stage"] == "Group"].copy()
    played_results = _played_results(results_df)

    counters = _empty_counters(teams)

    for _ in range(n_sims):
        sim_matches_by_group = {}
        sim_gf = defaultdict(float)
        sim_ga = defaultdict(float)

        for group, group_teams in groups.items():
            matches = []
            fixtures = group_fixtures[group_fixtures["Group"] == group]
            for fixture in fixtures.to_dict("records"):
                home = fixture["HomeTeam"]
                away = fixture["AwayTeam"]
                if fixture["MatchID"] in played_results:
                    hg, ag = played_results[fixture["MatchID"]]
                else:
                    dist = model.predict(home, away, neutral=bool(fixture["Neutral"]))
                    hg, ag = dist.sample(rng)
                matches.append(
                    {
                        "group": group,
                        "home": home,
                        "away": away,
                        "hg": int(hg),
                        "ag": int(ag),
                    }
                )
                sim_gf[home] += hg
                sim_ga[home] += ag
                sim_gf[away] += ag
                sim_ga[away] += hg
            sim_matches_by_group[group] = matches

        group_results = {}
        thirds = []
        r32_teams = set()

        for group, matches in sim_matches_by_group.items():
            ordered, stats = rank_group(matches, fifa_ranks)
            for idx, team in enumerate(ordered, start=1):
                counters[team]["positions"][idx] += 1

            winner, runner_up, third = ordered[:3]
            counters[winner]["won_group"] += 1
            counters[winner]["top2_in_group"] += 1
            counters[runner_up]["top2_in_group"] += 1
            r32_teams.update((winner, runner_up))

            group_results[group] = {
                "winner": winner,
                "runner_up": runner_up,
                "third": third,
            }
            thirds.append(stats[third])

        if len(groups) < 12:
            winner_fn = _winner_fn(model, rng, shootout, elo, sim_gf, sim_ga)
            _simulate_mini_knockout(group_results, counters, winner_fn)
            for team in teams:
                counters[team]["gf"] += sim_gf[team]
                counters[team]["ga"] += sim_ga[team]
            continue

        best_thirds, _ = rank_third_place(thirds, fifa_ranks)
        r32_teams.update(best_thirds)
        for team in r32_teams:
            counters[team]["reached_R32"] += 1

        r32 = build_r32(group_results, best_thirds)
        winner_fn = _winner_fn(model, rng, shootout, elo, sim_gf, sim_ga)
        r16, _ = advance(r32, winner_fn)
        _record_pairing_teams(counters, r16, "reached_R16")
        qf, _ = advance(r16, winner_fn)
        _record_pairing_teams(counters, qf, "reached_QF")
        sf, _ = advance(qf, winner_fn)
        _record_pairing_teams(counters, sf, "reached_SF")
        final, third_place = advance(sf, winner_fn)
        _record_pairing_teams(counters, final, "reached_Final")
        champion_pairing, _ = advance(final, winner_fn)
        champion = champion_pairing[0][0]
        counters[champion]["won_cup"] += 1

        # Simulate the 3rd-place playoff for completeness, but it does not feed the
        # requested stage counters.
        if third_place:
            advance(third_place, winner_fn)

        for team in teams:
            counters[team]["gf"] += sim_gf[team]
            counters[team]["ga"] += sim_ga[team]

    result = _aggregate(counters, groups, n_sims)
    _write_cache(cache_key, result)
    return result


def _winner_fn(
    model,
    rng,
    shootout: str,
    elo: dict[str, float],
    goals_for: dict[str, float],
    goals_against: dict[str, float],
):
    def choose(team_a: str, team_b: str) -> tuple[str, str]:
        dist = model.predict(team_a, team_b, neutral=True)
        goals_a, goals_b = dist.sample(rng)
        goals_for[team_a] += goals_a
        goals_against[team_a] += goals_b
        goals_for[team_b] += goals_b
        goals_against[team_b] += goals_a
        if goals_a > goals_b:
            return team_a, team_b
        if goals_b > goals_a:
            return team_b, team_a
        p_a = _shootout_probability(team_a, team_b, shootout, elo)
        if rng.random() < p_a:
            return team_a, team_b
        return team_b, team_a

    return choose


def _simulate_mini_knockout(
    group_results: dict,
    counters: dict[str, dict],
    winner_fn,
) -> None:
    groups = sorted(group_results)
    qualifiers = []
    for group in groups:
        winner = group_results[group]["winner"]
        runner_up = group_results[group]["runner_up"]
        qualifiers.extend((winner, runner_up))
        counters[winner]["reached_R32"] += 1
        counters[runner_up]["reached_R32"] += 1

    if len(qualifiers) < 2:
        return
    if len(groups) == 2:
        pairings = [
            (group_results[groups[0]]["winner"], group_results[groups[1]]["runner_up"]),
            (group_results[groups[1]]["winner"], group_results[groups[0]]["runner_up"]),
        ]
    else:
        pairings = list(zip(qualifiers[::2], qualifiers[1::2]))

    while len(pairings) > 1:
        _record_pairing_teams(counters, pairings, "reached_R16")
        pairings, _ = advance(pairings, winner_fn)

    _record_pairing_teams(counters, pairings, "reached_Final")
    champion_pairing, _ = advance(pairings, winner_fn)
    champion = champion_pairing[0][0]
    counters[champion]["won_cup"] += 1


def _shootout_probability(
    team_a: str,
    team_b: str,
    shootout: str,
    elo: dict[str, float],
) -> float:
    if shootout == "coin":
        return 0.5
    if shootout != "elo":
        raise ValueError("shootout must be 'elo' or 'coin'")

    # Small Elo shootout edge: 100 Elo points moves a shootout from 50/50 to 57/43,
    # clipped so underdogs always retain a realistic path.
    elo_a = float(elo.get(team_a, 0))
    elo_b = float(elo.get(team_b, 0))
    return min(0.95, max(0.05, 0.5 + SHOOTOUT_ELO_K * (elo_a - elo_b)))


def _played_results(results_df: pd.DataFrame) -> dict[int, tuple[int, int]]:
    if results_df.empty:
        return {}
    played = results_df.dropna(subset=["FTHG", "FTAG"])
    return {
        int(row["MatchID"]): (int(row["FTHG"]), int(row["FTAG"]))
        for row in played.to_dict("records")
    }


def _empty_counters(teams: list[str]) -> dict[str, dict]:
    return {
        team: {
            "reached_R32": 0,
            "reached_R16": 0,
            "reached_QF": 0,
            "reached_SF": 0,
            "reached_Final": 0,
            "won_cup": 0,
            "won_group": 0,
            "top2_in_group": 0,
            "positions": {1: 0, 2: 0, 3: 0, 4: 0},
            "gf": 0.0,
            "ga": 0.0,
        }
        for team in teams
    }


def _record_pairing_teams(counters: dict[str, dict], pairings: list[tuple], key: str) -> None:
    for pairing in pairings:
        for team in pairing:
            counters[team][key] += 1


def _aggregate(counters: dict[str, dict], groups: dict[str, list[str]], n_sims: int) -> dict:
    per_team = {}
    for team, counts in counters.items():
        per_team[team] = {
            "P(advance)": counts["reached_R32"] / n_sims,
            "P(win_group)": counts["won_group"] / n_sims,
            "P(top2_in_group)": counts["top2_in_group"] / n_sims,
            "P(reach_R16)": counts["reached_R16"] / n_sims,
            "P(reach_QF)": counts["reached_QF"] / n_sims,
            "P(reach_SF)": counts["reached_SF"] / n_sims,
            "P(reach_Final)": counts["reached_Final"] / n_sims,
            "P(win_cup)": counts["won_cup"] / n_sims,
            "xGF": counts["gf"] / n_sims,
            "xGA": counts["ga"] / n_sims,
            "finish_distribution": {
                "1st": counts["positions"][1] / n_sims,
                "2nd": counts["positions"][2] / n_sims,
                "3rd": counts["positions"][3] / n_sims,
                "4th": counts["positions"][4] / n_sims,
            },
        }

    per_group = {}
    for group, teams in groups.items():
        per_group[group] = {
            team: per_team[team]["finish_distribution"] for team in teams
        }

    return {"per_team": per_team, "per_group": per_group}


def _cache_key(model, n_sims: int, results_df: pd.DataFrame) -> str:
    model_name = model.__class__.__name__
    results_hash = hashlib.sha256(
        results_df.to_csv(index=False).encode("utf-8")
    ).hexdigest()
    raw_key = json.dumps(
        {
            "model_name": model_name,
            "n_sims": n_sims,
            "results_hash": results_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _read_cache(cache_key: str) -> dict | None:
    if not CACHE_PATH.exists():
        return None
    with CACHE_PATH.open("r", encoding="utf-8") as f:
        cache = json.load(f)
    entry = cache.get(cache_key)
    if entry is None:
        return None
    return entry["result"]


def _write_cache(cache_key: str, result: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_PATH.exists():
        with CACHE_PATH.open("r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}
    cache[cache_key] = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    with CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    groups = load_groups()
    fixtures = load_fixtures()
    results = load_results()
    elo = load_elo()
    fifa_ranks = dict(zip(groups["Team"], groups["FIFA_Rank"]))
    simulation = simulate_tournament(
        EloModel(elo),
        groups,
        fixtures,
        results,
        fifa_ranks,
        n_sims=2000,
        seed=42,
        shootout="elo",
        elo=elo,
    )
    leaderboard = sorted(
        simulation["per_team"].items(),
        key=lambda item: item[1]["P(win_cup)"],
        reverse=True,
    )[:15]
    print("World Cup win-cup leaderboard")
    for idx, (team, stats) in enumerate(leaderboard, start=1):
        print(f"{idx:2d}. {team}: {stats['P(win_cup)']:.3f}")
