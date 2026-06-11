"""Streamlit UI for the World Cup 2026 tab."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from worldcup.data import load_elo, load_fixtures, load_groups, load_results
from worldcup.historical import load_history
from worldcup.models import AVAILABLE_MODELS
from worldcup.models import STRENGTHS_PATH
from worldcup.model import EloModel
from worldcup.models.bradley_terry import BradleyTerryModel
from worldcup.models.dixon_coles import DixonColesModel
from worldcup.models.poisson import PoissonModel
from worldcup.simulate import simulate_tournament
from worldcup.strengths import load_strengths
from worldcup.validation import backtest, compare_models
from worldcup.viz import (
    favorite_metric,
    group_exit_table,
    group_projection,
    most_likely_bracket,
)
from worldcup.insights import (
    overperformers_underperformers,
    title_contenders,
)

MODEL_CAPTIONS = {
    "Elo-Poisson": "Elo-Poisson anchors scorelines to seed ratings and preserves Elo W/D/L probabilities.",
    "Data Poisson": "Data Poisson uses empirical attack and defense strengths from recent international results.",
    "Dixon-Coles": "Dixon-Coles is the flagship score model, adding low-score correlation to data Poisson rates.",
    "Bradley-Terry": "Bradley-Terry is a comparison model that fits W/D/L strength and reshapes goal rates.",
}


def render_worldcup_tab():
    st.title("World Cup 2026 Predictor")
    st.markdown("A Monte Carlo forecast for the 48-team tournament.")

    groups = load_groups()
    fixtures = load_fixtures()
    results = load_results()
    elo = load_elo()
    fifa_ranks = dict(zip(groups["Team"], groups["FIFA_Rank"]))

    model_name = st.sidebar.selectbox("World Cup match model", list(AVAILABLE_MODELS))
    st.sidebar.caption(MODEL_CAPTIONS[model_name])
    n_sims = st.sidebar.number_input(
        "World Cup simulations",
        min_value=100,
        max_value=20000,
        value=2000,
        step=100,
    )

    simulation = _cached_simulation(
        model_name,
        groups,
        fixtures,
        results,
        fifa_ranks,
        n_sims=int(n_sims),
        elo=elo,
    )

    favorite = favorite_metric(simulation)
    st.info(favorite["headline"])
    st.metric(
        "Current favorite",
        favorite["team"],
        f"{favorite['p_win_cup']:.1%} win-cup probability",
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

    _render_validation(model_name)
    _render_tournament_projection(simulation)

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

    st.header("Overachievers vs. Underachievers")
    ou = overperformers_underperformers(simulation, fifa_ranks)
    with st.expander("Overachievers", expanded=False):
        for entry in ou.get("overperformers", []):
            st.write(f"**{entry['team']}** — {entry['reason']}")
    with st.expander("Underachievers", expanded=False):
        for entry in ou.get("underperformers", []):
            st.write(f"**{entry['team']}** — {entry['reason']}")


@st.cache_data(show_spinner="Running World Cup simulations...")
def _cached_simulation(
    model_name: str,
    groups: pd.DataFrame,
    fixtures: pd.DataFrame,
    results: pd.DataFrame,
    fifa_ranks: dict[str, int],
    n_sims: int,
    elo: dict[str, float],
) -> dict:
    model = AVAILABLE_MODELS[model_name]()
    return simulate_tournament(
        model,
        groups,
        fixtures,
        results,
        fifa_ranks,
        n_sims=int(n_sims),
        seed=42,
        shootout="elo",
        elo=elo,
    )


@st.cache_data(show_spinner="Backtesting match models...")
def _cached_validation() -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    history = load_history()
    factories = _validation_model_factories()
    rows = compare_models(factories, history)
    calibration = {
        name: backtest(factory, history)["calibration_bins"]
        for name, factory in factories.items()
    }
    return rows, calibration


def _validation_model_factories():
    strengths = load_strengths(STRENGTHS_PATH)
    elo = load_elo()
    return {
        "Elo-Poisson": lambda: EloModel(elo),
        "Data Poisson": lambda: PoissonModel(strengths),
        "Dixon-Coles": lambda: DixonColesModel(strengths),
        "Bradley-Terry": lambda: BradleyTerryModel.from_elo(strengths, elo),
    }


def _render_validation(model_name: str) -> None:
    with st.expander("Model Validation", expanded=False):
        try:
            validation, calibration = _cached_validation()
        except FileNotFoundError:
            st.info(
                "Historical match cache not found. Run `python -m worldcup.strengths` "
                "once to download history before viewing validation."
            )
            return

        display = validation[["Model", "LogLoss", "Brier", "RPS"]].copy()
        display[["LogLoss", "Brier", "RPS"]] = display[
            ["LogLoss", "Brier", "RPS"]
        ].round(4)
        best_model = display.iloc[0]["Model"] if not display.empty else None
        st.dataframe(
            display.style.apply(
                lambda row: [
                    "background-color: #e8f5e9" if row["Model"] == best_model else ""
                    for _ in row
                ],
                axis=1,
            ),
            use_container_width=True,
            hide_index=True,
        )

        bins = pd.DataFrame(calibration.get(model_name, []))
        if not bins.empty:
            chart_df = bins[["mean_confidence", "observed_frequency"]].rename(
                columns={
                    "mean_confidence": "Predicted confidence",
                    "observed_frequency": "Observed frequency",
                }
            )
            st.line_chart(chart_df, x="Predicted confidence", y="Observed frequency")


def _render_tournament_projection(simulation: dict) -> None:
    st.header("Tournament Projection")
    st.subheader("Group Stage")
    for group in sorted(simulation.get("per_group", {})):
        projection = group_projection(simulation, group)
        with st.expander(f"Group {group}", expanded=False):
            st.markdown(projection["narrative"])
            standings = pd.DataFrame(projection["standings"])
            st.dataframe(
                standings[
                    [
                        "Projected Rank",
                        "Team",
                        "Tag",
                        "P(advance)",
                        "P(win_group)",
                        "Projected Finish",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "P(advance)": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
                    "P(win_group)": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
                },
            )
            finish = pd.DataFrame(projection["finish_distribution"])
            if not finish.empty:
                finish_pivot = finish.pivot(
                    index="Team",
                    columns="Finish",
                    values="Probability",
                ).fillna(0)
                st.bar_chart(finish_pivot, use_container_width=True)

    st.subheader("Knockout Projection")
    bracket = most_likely_bracket(simulation)
    rounds = bracket.get("rounds", {})
    if rounds:
        cols = st.columns(len(rounds))
        for col, (round_name, pairings) in zip(cols, rounds.items()):
            with col:
                st.markdown(f"**{round_name}**")
                for pairing in pairings:
                    st.write(" vs ".join(pairing))
    champion = bracket.get("champion")
    if champion:
        p_win = simulation["per_team"].get(champion, {}).get("P(win_cup)", 0.0)
        st.success(f"Projected champion: {champion} ({p_win:.1%})")

    st.subheader("Who gets out of the group?")
    exit_table = pd.DataFrame(group_exit_table(simulation))
    st.dataframe(
        exit_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "P(advance)": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
        },
    )
