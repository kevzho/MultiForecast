"""Streamlit UI for the World Cup 2026 tab."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from time import perf_counter, time

from worldcup.data import load_elo, load_fixtures, load_groups, load_results
from worldcup.historical import load_history
from worldcup.models import AVAILABLE_MODELS
from worldcup.models import STRENGTHS_PATH
from worldcup.model import EloModel
from worldcup.models.bradley_terry import BradleyTerryModel
from worldcup.models.dixon_coles import DixonColesModel
from worldcup.models.poisson import PoissonModel
from worldcup.simulate import simulate_tournament, simulation_cache_info
from worldcup.strengths import load_strengths
from worldcup.validation import backtest, compare_models
from worldcup.viz import (
    all_team_probabilities,
    favorite_metric,
    group_projection,
    most_likely_bracket,
)
from worldcup.insights import (
    headline,
    title_contenders,
)

MODEL_CAPTIONS = {
    "Elo-Poisson": "Elo-Poisson anchors scorelines to seed ratings and preserves Elo W/D/L probabilities.",
    "Data Poisson": "Data Poisson uses empirical attack and defense strengths from recent international results.",
    "Dixon-Coles": "Dixon-Coles is the flagship score model, adding low-score correlation to data Poisson rates.",
    "Bradley-Terry": "Bradley-Terry is a comparison model that fits W/D/L strength and reshapes goal rates.",
}
MODEL_CACHE_CLASS_NAMES = {
    "Elo-Poisson": "EloModel",
    "Data Poisson": "PoissonModel",
    "Dixon-Coles": "DixonColesModel",
    "Bradley-Terry": "BradleyTerryModel",
}


def render_worldcup_tab():
    groups = load_groups()
    fixtures = load_fixtures()
    results = load_results()
    elo = load_elo()
    fifa_ranks = dict(zip(groups["Team"], groups["FIFA_Rank"]))

    model_names = list(AVAILABLE_MODELS)
    default_model = "Elo-Poisson" if "Elo-Poisson" in AVAILABLE_MODELS else model_names[0]
    with st.sidebar:
        st.header("World Cup Forecast")
        st.caption("Choose the match model and simulation volume for the tournament projection.")
        model_name = st.selectbox(
            "Model",
            model_names,
            index=model_names.index(default_model),
            help="Selects the match model used by the cached Monte Carlo tournament simulation.",
        )
        st.caption(MODEL_CAPTIONS[model_name])
        st.divider()
        st.subheader("Simulation Settings")
        n_sims = st.number_input(
            "Simulations",
            min_value=100,
            max_value=20000,
            value=2000,
            step=100,
            help="Higher values smooth the forecast but take longer on a cache miss.",
        )

    n_sims = int(n_sims)
    selection_key = (model_name, n_sims)
    cache_info = _cached_simulation_cache_info(model_name, n_sims, results)
    with st.sidebar:
        if cache_info:
            ran_at = cache_info.get("last_updated") or "an earlier run"
            seed_note = cache_info.get("seed")
            seed_text = f", seed {seed_note}" if seed_note is not None else ""
            st.caption(f"Cached result available ({ran_at}{seed_text}); Run simulation will load it.")
        run_clicked = st.button("Run simulation", type="primary", use_container_width=True)
        rerun_clicked = False
        if cache_info:
            rerun_clicked = st.button("Re-run", use_container_width=True)

    if run_clicked or rerun_clicked:
        seed = int(time()) if rerun_clicked else 42
        start = perf_counter()
        with st.spinner("Running World Cup simulation..."):
            simulation = _cached_simulation(
                model_name,
                groups,
                fixtures,
                results,
                fifa_ranks,
                n_sims=n_sims,
                elo=elo,
                seed=seed,
                force=rerun_clicked,
                cache_token=_cache_token(cache_info),
            )
        elapsed = perf_counter() - start
        st.session_state["worldcup_simulation"] = {
            "key": selection_key,
            "result": simulation,
            "metadata": _cached_simulation_cache_info(model_name, n_sims, results) or {
                "seed": seed,
                "last_updated": None,
            },
            "elapsed": elapsed,
            "forced": rerun_clicked,
        }

    state = st.session_state.get("worldcup_simulation")
    if not state or state.get("key") != selection_key:
        st.title("World Cup 2026 Predictor")
        st.info("Pick a model and click Run simulation to generate the forecast.")
        return

    simulation = state["result"]
    metadata = state.get("metadata") or {}
    if metadata.get("last_updated"):
        st.caption(
            f"Showing cached results from {metadata['last_updated']} "
            f"(seed {metadata.get('seed', 'unknown')})."
        )
    elif state.get("elapsed") is not None:
        st.caption(f"Simulation completed in {state['elapsed']:.1f}s.")

    bracket = most_likely_bracket(simulation)

    st.title("World Cup 2026 Predictor")
    st.markdown(f"### {headline(simulation)}")
    _render_hero_metrics(simulation, bracket)

    st.divider()
    _render_title_contenders(simulation)

    st.divider()
    _render_all_team_probabilities(simulation)

    st.divider()
    _render_group_stage(simulation)

    st.divider()
    _render_knockout_projection(simulation, bracket)

    st.divider()
    _render_validation(model_name)
    _render_methodology(model_name)


@st.cache_data(show_spinner="Running World Cup simulations...")
def _cached_simulation(
    model_name: str,
    groups: pd.DataFrame,
    fixtures: pd.DataFrame,
    results: pd.DataFrame,
    fifa_ranks: dict[str, int],
    n_sims: int,
    elo: dict[str, float],
    seed: int,
    force: bool,
    cache_token: str,
) -> dict:
    model = AVAILABLE_MODELS[model_name]()
    return simulate_tournament(
        model,
        groups,
        fixtures,
        results,
        fifa_ranks,
        n_sims=int(n_sims),
        seed=seed,
        shootout="elo",
        elo=elo,
        force=force,
    )


def _cached_simulation_cache_info(
    model_name: str,
    n_sims: int,
    results: pd.DataFrame,
) -> dict | None:
    model = _cache_key_model(model_name)
    return simulation_cache_info(model, int(n_sims), results)


def _cache_token(cache_info: dict | None) -> str:
    if not cache_info:
        return "miss"
    return str(cache_info.get("last_updated") or "unknown")


def _cache_key_model(model_name: str):
    class_name = MODEL_CACHE_CLASS_NAMES.get(model_name, model_name)
    return type(class_name, (), {})()


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


def _render_hero_metrics(simulation: dict, bracket: dict) -> None:
    favorite = favorite_metric(simulation)
    champion = bracket.get("champion") or favorite["team"]
    champion_prob = simulation.get("per_team", {}).get(champion, {}).get("P(win_cup)", 0.0)
    finalist, finalist_stats = max(
        simulation.get("per_team", {}).items(),
        key=lambda item: item[1].get("P(reach_Final)", 0.0),
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Favorite", favorite["team"], f"{favorite['p_win_cup']:.0%} win cup")
    with col2:
        st.metric("Projected Champion", champion, f"{champion_prob:.0%} win cup")
    with col3:
        st.metric(
            "Most Likely Finalist",
            finalist,
            f"{finalist_stats.get('P(reach_Final)', 0.0):.0%} reach final",
        )


def _render_title_contenders(simulation: dict) -> None:
    st.header("Title Contenders")
    st.caption("The top teams by simulated probability of lifting the trophy.")
    contenders = title_contenders(simulation, top_n=10)
    if not contenders:
        st.info("No title contender data available.")
        return

    df_contenders = pd.DataFrame(contenders).rename(
        columns={
            "team": "Team",
            "p_win_cup": "Win Cup",
            "p_reach_final": "Reach Final",
            "p_reach_sf": "Reach SF",
        }
    )
    chart = (
        alt.Chart(df_contenders)
        .mark_bar(color="#16a34a")
        .encode(
            x=alt.X("Win Cup:Q", axis=alt.Axis(format=".0%"), title="Win Cup"),
            y=alt.Y("Team:N", sort="-x", title=None),
            tooltip=[
                alt.Tooltip("Team:N"),
                alt.Tooltip("Win Cup:Q", format=".1%"),
                alt.Tooltip("Reach Final:Q", format=".1%"),
                alt.Tooltip("Reach SF:Q", format=".1%"),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)
    table = df_contenders.copy()
    for column in ("Win Cup", "Reach Final", "Reach SF"):
        table[column] = table[column] * 100
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Win Cup": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
            "Reach Final": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
            "Reach SF": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
        },
    )


def _render_all_team_probabilities(simulation: dict) -> None:
    st.header("All Teams — Win Probabilities")
    st.caption("Every team in the simulation, sorted by probability of winning the World Cup.")
    rows = all_team_probabilities(simulation)
    if not rows:
        st.info("No team probability data available.")
        return

    chart_df = pd.DataFrame(rows)
    chart = (
        alt.Chart(chart_df)
        .mark_bar(color="#15803d")
        .encode(
            x=alt.X("P(win_cup):Q", axis=alt.Axis(format=".0%"), title="Win Cup"),
            y=alt.Y("Team:N", sort="-x", title=None),
            tooltip=[
                alt.Tooltip("Team:N"),
                alt.Tooltip("Group:N"),
                alt.Tooltip("P(win_cup):Q", format=".1%"),
                alt.Tooltip("P(reach_Final):Q", format=".1%"),
            ],
        )
        .properties(height=max(480, len(chart_df) * 14))
    )
    st.altair_chart(chart, use_container_width=True)

    table = chart_df.copy()
    probability_columns = [
        "P(advance)",
        "P(reach_QF)",
        "P(reach_SF)",
        "P(reach_Final)",
        "P(win_cup)",
    ]
    for column in probability_columns:
        table[column] = table[column] * 100
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            column: st.column_config.ProgressColumn(
                format="%.1f%%",
                min_value=0,
                max_value=100,
            )
            for column in probability_columns
        },
    )


def _render_group_stage(simulation: dict) -> None:
    st.header("Group Stage")
    st.caption("Projected group tables combine advancement probability with most likely finish.")
    groups = sorted(simulation.get("per_group", {}))
    if not groups:
        st.info("No group projection data available.")
        return

    for start in range(0, len(groups), 4):
        cols = st.columns(4)
        for col, group in zip(cols, groups[start : start + 4]):
            projection = group_projection(simulation, group)
            with col:
                st.subheader(f"Group {group}")
                st.caption(projection["narrative"])
                standings = pd.DataFrame(projection["standings"])
                if not standings.empty:
                    display = standings[
                        [
                            "Projected Rank",
                            "Team",
                            "Tag",
                            "P(advance)",
                            "P(win_group)",
                        ]
                    ].copy()
                    display["Tag"] = display["Tag"].replace({"": "-"})
                    for column in ("P(advance)", "P(win_group)"):
                        display[column] = display[column] * 100
                    st.dataframe(
                        display,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "P(advance)": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                            "P(win_group)": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                        },
                    )
                finish = pd.DataFrame(projection["finish_distribution"])
                if not finish.empty:
                    chart = (
                        alt.Chart(finish)
                        .mark_bar()
                        .encode(
                            x=alt.X("Probability:Q", stack="normalize", axis=None),
                            y=alt.Y("Team:N", sort=None, title=None),
                            color=alt.Color(
                                "Finish:N",
                                scale=alt.Scale(
                                    domain=["1st", "2nd", "3rd", "4th"],
                                    range=["#16a34a", "#65a30d", "#f59e0b", "#94a3b8"],
                                ),
                            ),
                            tooltip=[
                                alt.Tooltip("Team:N"),
                                alt.Tooltip("Finish:N"),
                                alt.Tooltip("Probability:Q", format=".1%"),
                            ],
                        )
                        .properties(height=96)
                    )
                    st.altair_chart(chart, use_container_width=True)


def _render_knockout_projection(simulation: dict, bracket: dict) -> None:
    st.header("Knockout Projection")
    st.caption("Each matchup advances the team with the stronger projected next-round probability.")
    rounds = bracket.get("rounds", {})
    left_rounds = rounds.get("left", {})
    right_rounds = rounds.get("right", {})
    final = rounds.get("Final", [])
    if left_rounds or right_rounds:
        cols = st.columns([1.25, 1.1, 0.95, 0.85, 1.05, 0.85, 0.95, 1.1, 1.25])
        left_order = ("R32", "R16", "QF", "SF")
        right_order = ("SF", "QF", "R16", "R32")
        for col, round_name in zip(cols[:4], left_order):
            with col:
                _render_bracket_round(round_name, left_rounds.get(round_name, []))
        with cols[4]:
            st.markdown("**Final**")
            for matchup in final:
                _render_matchup_card(matchup, compact=False)
            champion = bracket.get("champion")
            if champion:
                p_win = simulation["per_team"].get(champion, {}).get("P(win_cup)", 0.0)
                st.success(f"🏆 **{champion}**\n\n{p_win:.0%} win-cup probability")
        for col, round_name in zip(cols[5:], right_order):
            with col:
                _render_bracket_round(round_name, right_rounds.get(round_name, []))


def _render_bracket_round(round_name: str, matchups: list[dict]) -> None:
    st.markdown(f"**{round_name}**")
    spacer = {"R32": 0.25, "R16": 1.0, "QF": 2.4, "SF": 4.2}.get(round_name, 0.25)
    if spacer:
        st.markdown(f"<div style='height:{spacer}rem;'></div>", unsafe_allow_html=True)
    for matchup in matchups:
        _render_matchup_card(matchup)


def _render_matchup_card(matchup: dict, compact: bool = True) -> None:
    team_a = matchup["team_a"]
    team_b = matchup["team_b"]
    winner = matchup["winner"]
    loser = team_b if winner == team_a else team_a
    probability = matchup.get("p_advance_winner", 0.0)
    margin = "0.5rem" if compact else "0.8rem"
    st.markdown(
        f"""
        <div style="border:1px solid #e5e7eb;border-left:4px solid #16a34a;border-radius:8px;padding:0.55rem 0.65rem;margin-bottom:{margin};background:#ffffff;">
          <div style="font-weight:700;color:#15803d;">✅ {winner} <span style="float:right;">{probability:.0%}</span></div>
          <div style="color:#94a3b8;text-decoration:line-through;margin-top:0.15rem;">{loser}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_methodology(model_name: str) -> None:
    with st.expander("Methodology", expanded=False):
        st.caption("Shared scoreline model")
        st.latex(r"P(k) = \frac{\lambda^{k} e^{-\lambda}}{k!}")
        st.write("Poisson rates turn team strength into a full scoreline probability grid.")

        if model_name == "Elo-Poisson":
            st.caption("Elo win expectation")
            st.latex(r"E_A = \frac{1}{1 + 10^{(R_B - R_A)/400}}")
            st.write("Elo ratings set the match win balance before the score grid is rescaled.")
        elif model_name == "Data Poisson":
            st.caption("Skellam goal-difference check")
            st.latex(
                r"P(X_h - X_a = z) = e^{-(\lambda_h+\lambda_a)}\left(\frac{\lambda_h}{\lambda_a}\right)^{z/2} I_{|z|}\!\left(2\sqrt{\lambda_h\lambda_a}\right)"
            )
            st.write("The Skellam distribution summarizes win, draw, and loss probabilities from two Poisson rates.")
        elif model_name == "Dixon-Coles":
            st.caption("Dixon-Coles low-score correction")
            st.latex(
                r"\tau(x,y)=\begin{cases}1-\lambda_h\lambda_a\rho&(0,0)\\1+\lambda_h\rho&(0,1)\\1+\lambda_a\rho&(1,0)\\1-\rho&(1,1)\\1&\text{else}\end{cases}"
            )
            st.write("Dixon-Coles adjusts the low-score cells that independent Poisson models tend to misstate.")
        elif model_name == "Bradley-Terry":
            st.caption("Bradley-Terry comparison")
            st.latex(r"P(i\succ j)=\frac{\pi_i}{\pi_i+\pi_j}")
            st.write("Bradley-Terry estimates team comparison strength and uses it to reshape win/draw/loss mass.")
