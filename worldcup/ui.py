"""Streamlit UI for the World Cup 2026 tab."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from worldcup.data import load_elo, load_fixtures, load_groups, load_results
from worldcup.model import EloModel
from worldcup.simulate import simulate_tournament
from worldcup.insights import (
    group_stage_narrative,
    qualification_table,
    title_contenders,
    overperformers_underperformers,
    headline,
)


def render_worldcup_tab():
    st.title("World Cup 2026 Predictor")
    st.markdown("A Monte Carlo forecast for the 48-team tournament.")

    groups = load_groups()
    fixtures = load_fixtures()
    results = load_results()
    elo = load_elo()
    fifa_ranks = dict(zip(groups["Team"], groups["FIFA_Rank"]))

    n_sims = st.sidebar.number_input(
        "World Cup simulations",
        min_value=100,
        max_value=20000,
        value=2000,
        step=100,
    )

    simulation = simulate_tournament(
        EloModel(elo),
        groups,
        fixtures,
        results,
        fifa_ranks,
        n_sims=int(n_sims),
        seed=42,
        shootout="elo",
        elo=elo,
    )

    leaderboard = pd.DataFrame(
        [
            {
                "Team": team,
                "Win Cup": stats["P(win_cup)"],
                "Reach Final": stats["P(reach_Final)"],
                "Reach SF": stats["P(reach_SF)"],
                "Advance": stats["P(advance)"],
            }
            for team, stats in simulation["per_team"].items()
        ]
    ).sort_values("Win Cup", ascending=False)

    st.header("Win-Cup Leaderboard")
    st.dataframe(
        leaderboard.head(15),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Win Cup": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
            "Reach Final": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
            "Reach SF": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
            "Advance": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
        },
    )

    # Tournament Outlook
    st.header("Tournament Outlook")
    st.markdown(headline(simulation))

    contenders = title_contenders(simulation, top_n=8)
    if contenders:
        df_contenders = pd.DataFrame(contenders)
        st.subheader("Title Contenders")
        st.dataframe(
            df_contenders,
            use_container_width=True,
            hide_index=True,
            column_config={
                "p_win_cup": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
                "p_reach_final": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
                "p_reach_sf": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
            },
        )

    st.header("Groups")
    for group, group_df in groups.groupby("Group", sort=True):
        with st.expander(f"Group {group}", expanded=False):
            # group narrative and qualification table
            st.markdown(group_stage_narrative(simulation, group))
            qual_rows = qualification_table(simulation, group)
            if qual_rows:
                dfq = pd.DataFrame(qual_rows)
                st.dataframe(
                    dfq,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "p_advance": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
                    },
                )

            st.dataframe(group_df[["Team", "FIFA_Rank", "Confederation"]], hide_index=True)

    # Over/Under performers
    st.header("Overachievers vs. Underachievers")
    ou = overperformers_underperformers(simulation, fifa_ranks)
    with st.expander("Overachievers", expanded=False):
        for entry in ou.get("overperformers", []):
            st.write(f"**{entry['team']}** — {entry['reason']}")
    with st.expander("Underachievers", expanded=False):
        for entry in ou.get("underperformers", []):
            st.write(f"**{entry['team']}** — {entry['reason']}")
