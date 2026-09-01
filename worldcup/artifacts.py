"""Web artifact export for the World Cup forecast."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

import numpy as np
import pandas as pd

from worldcup.data import load_elo, load_fixtures, load_groups, load_results
from worldcup.models import AVAILABLE_MODELS
from worldcup.simulate import simulate_tournament
from worldcup.viz import most_likely_bracket


SCHEMA_VERSION = "1.0.0"
ARTIFACT_VERSION = "2026.1"


def _id(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return text or "unknown"


def _team_ref(team: str) -> dict[str, str]:
    return {"id": _id(team), "name": team, "shortName": team}


def _scoreline_forecast(dist: Any) -> dict[str, Any]:
    grid = np.asarray(dist.grid, dtype=float)
    home_axis = np.arange(grid.shape[0], dtype=float)[:, None]
    away_axis = np.arange(grid.shape[1], dtype=float)[None, :]
    order = np.argsort(grid.ravel())[::-1][:5]
    scorelines = []
    for flat_index in order:
        home, away = np.unravel_index(int(flat_index), grid.shape)
        scorelines.append(
            {
                "home": int(home),
                "away": int(away),
                "probability": float(grid[home, away]),
            }
        )
    home_win, draw, away_win = dist.wdl
    return {
        "homeWin": float(home_win),
        "draw": float(draw),
        "awayWin": float(away_win),
        "expectedHomeGoals": float((grid * home_axis).sum()),
        "expectedAwayGoals": float((grid * away_axis).sum()),
        "over25": float(grid[(home_axis + away_axis > 2.0)].sum()),
        "bothTeamsScore": float(grid[1:, 1:].sum()),
        "homeCleanSheet": float(grid[:, 0].sum()),
        "awayCleanSheet": float(grid[0, :].sum()),
        "topScorelines": scorelines,
        "modelProbabilities": [],
        "seasonImpact": [],
    }


def _fixture_records(
    fixtures: pd.DataFrame,
    results: pd.DataFrame,
    model: Any,
    team_names: set[str],
) -> list[dict[str, Any]]:
    score_by_match = {}
    if not results.empty:
        played = results.dropna(subset=["FTHG", "FTAG"])
        score_by_match = {
            int(row.MatchID): (int(row.FTHG), int(row.FTAG))
            for row in played.itertuples(index=False)
        }

    records = []
    for row in fixtures.itertuples(index=False):
        match_id = int(row.MatchID)
        home = str(row.HomeTeam)
        away = str(row.AwayTeam)
        resolved = home in team_names and away in team_names
        score = score_by_match.get(match_id)
        forecast = None
        if resolved:
            forecast = _scoreline_forecast(
                model.predict(home, away, neutral=bool(row.Neutral))
            )
        kickoff = pd.Timestamp(row.Date).strftime("%Y-%m-%dT00:00:00Z")
        records.append(
            {
                "id": f"wc-{match_id}",
                "stage": str(row.Stage),
                "round": str(row.Group) if pd.notna(row.Group) else None,
                "kickoff": kickoff,
                "venue": None if str(row.Venue) == "TBD" else str(row.Venue),
                "status": "final" if score is not None else "scheduled",
                "homeTeam": _team_ref(home) if resolved else None,
                "awayTeam": _team_ref(away) if resolved else None,
                "homeSource": None if resolved else home,
                "awaySource": None if resolved else away,
                "score": (
                    {"home": score[0], "away": score[1]}
                    if score is not None
                    else None
                ),
                "forecast": forecast,
            }
        )
    return records


def _bracket_rounds(bracket: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    rounds = bracket.get("rounds", {})
    for side in ("left", "right"):
        side_rounds = rounds.get(side, {})
        for round_id in ("R32", "R16", "QF", "SF"):
            matches = side_rounds.get(round_id, [])
            if not matches:
                continue
            records.append(
                {
                    "id": f"{side}-{round_id.lower()}",
                    "label": f"{round_id} · {side.title()}",
                    "matches": [
                        {
                            "fixtureId": f"projected-{side}-{round_id.lower()}-{index}",
                            "homeSource": match["team_a"],
                            "awaySource": match["team_b"],
                        }
                        for index, match in enumerate(matches, start=1)
                    ],
                }
            )
    final = rounds.get("Final", [])
    if final:
        records.append(
            {
                "id": "final",
                "label": "Final",
                "matches": [
                    {
                        "fixtureId": f"projected-final-{index}",
                        "homeSource": match["team_a"],
                        "awaySource": match["team_b"],
                    }
                    for index, match in enumerate(final, start=1)
                ],
            }
        )
    return records


def build_worldcup_artifact(
    *,
    model_name: str = "Elo-Poisson",
    n_simulations: int = 2000,
    seed: int = 42,
    force: bool = False,
) -> dict[str, Any]:
    groups = load_groups()
    fixtures = load_fixtures()
    results = load_results()
    elo = load_elo()
    fifa_ranks = dict(zip(groups["Team"], groups["FIFA_Rank"]))
    model = AVAILABLE_MODELS[model_name]()
    simulation = simulate_tournament(
        model,
        groups,
        fixtures,
        results,
        fifa_ranks,
        n_sims=int(n_simulations),
        seed=int(seed),
        shootout="elo",
        elo=elo,
        force=force,
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    team_names = set(groups["Team"])
    team_rows = []
    for row in groups.itertuples(index=False):
        stats = simulation["per_team"][row.Team]
        team_rows.append(
            {
                "team": _team_ref(row.Team),
                "group": str(row.Group),
                "rating": float(elo[row.Team]) if row.Team in elo else None,
                "probabilities": {
                    "advanceGroup": float(stats["P(advance)"]),
                    "roundOf16": float(stats["P(reach_R16)"]),
                    "quarterfinal": float(stats["P(reach_QF)"]),
                    "semifinal": float(stats["P(reach_SF)"]),
                    "final": float(stats["P(reach_Final)"]),
                    "champion": float(stats["P(win_cup)"]),
                },
            }
        )

    group_rows = []
    for group, frame in groups.groupby("Group", sort=True):
        group_fixtures = fixtures[
            (fixtures["Stage"] == "Group") & (fixtures["Group"] == group)
        ]
        group_rows.append(
            {
                "id": str(group),
                "label": f"Group {group}",
                "teamIds": [_id(team) for team in frame["Team"]],
                "fixtureIds": [
                    f"wc-{int(match_id)}" for match_id in group_fixtures["MatchID"]
                ],
            }
        )

    return {
        "kind": "tournament-forecast",
        "schemaVersion": SCHEMA_VERSION,
        "artifactVersion": ARTIFACT_VERSION,
        "status": "ready",
        "isDemo": False,
        "disclaimer": "Tournament probabilities are model estimates, not guarantees.",
        "competition": {
            "id": "world-cup-2026",
            "name": "FIFA World Cup 2026",
            "shortName": "World Cup",
            "country": "Canada, Mexico and United States",
            "code": "WC2026",
        },
        "edition": "2026",
        "generatedAt": generated_at,
        "model": {
            "name": model_name,
            "version": ARTIFACT_VERSION,
            "simulations": int(n_simulations),
            "trainedThrough": None,
        },
        "coverage": {
            "teamsIncluded": len(team_rows),
            "teamsExpected": 48,
            "groupsIncluded": len(group_rows),
            "groupsExpected": 12,
        },
        "teams": team_rows,
        "groups": group_rows,
        "fixtures": _fixture_records(fixtures, results, model, team_names),
        "bracket": _bracket_rounds(most_likely_bracket(simulation)),
        "methodology": {
            "primaryModel": model_name,
            "components": [
                "Elo strength ratings",
                "Poisson scoreline distribution",
                "Monte Carlo group and knockout simulation",
                "FIFA group and third-place tiebreakers",
            ],
            "evaluation": "Models are compared with log loss, Brier score and RPS.",
            "assumptions": [
                "Listed venues determine whether host advantage is applied.",
                "Knockout shootouts use a small Elo-weighted advantage.",
            ],
        },
    }


__all__ = [
    "ARTIFACT_VERSION",
    "SCHEMA_VERSION",
    "build_worldcup_artifact",
]
