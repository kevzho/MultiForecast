"""Streamlit views for domestic league forecasts."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from domestic.config import list_leagues
from domestic.models import MODEL_NAMES
from domestic.pipeline import ForecastRun, build_breakdown_with_impact, build_forecast


MODEL_LABELS = {
    "auto": "Best backtested model",
    "elo": "Elo baseline",
    "elo_poisson": "Elo-Poisson",
    "poisson": "Attack-defense Poisson",
    "dixon_coles": "Dixon-Coles",
    "bradley_terry": "Bradley-Terry",
}


@st.cache_resource(show_spinner="Fitting models and simulating the season...")
def _cached_forecast(
    league: str,
    model: str,
    simulations: int,
    validate: bool,
) -> ForecastRun:
    return build_forecast(
        league,
        model_name=model,
        run_validation=validate,
        n_simulations=simulations,
        seed=42,
    )


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _forecast_table(run: ForecastRun) -> pd.DataFrame:
    current = {row["team"]: row for row in run.forecast.current_table}
    rows = []
    for team, forecast in run.forecast.teams.items():
        table = current.get(team, {})
        rows.append(
            {
                "Team": team,
                "MP": int(table.get("played", 0)),
                "Pts": int(table.get("points", 0)),
                "Projected Pts": forecast.expected_points,
                "Projected Pos": forecast.expected_position,
                "Title": forecast.title_probability,
                "Champions League": forecast.qualification_probabilities.get(
                    "champions_league", 0.0
                ),
                "Relegation": forecast.relegation_probability,
            }
        )
    frame = pd.DataFrame(rows).sort_values(
        ["Projected Pos", "Projected Pts"], ascending=[True, False]
    )
    frame.insert(0, "Pos", range(1, len(frame) + 1))
    return frame


def _render_overview(run: ForecastRun) -> None:
    table = _forecast_table(run)
    title_favorite = max(
        run.forecast.teams.values(), key=lambda item: item.title_probability
    )
    champions_favorite = max(
        run.forecast.teams.values(),
        key=lambda item: item.qualification_probabilities.get("champions_league", 0.0),
    )
    relegation_favorite = max(
        run.forecast.teams.values(), key=lambda item: item.relegation_probability
    )

    columns = st.columns(4)
    columns[0].metric(
        "Title favorite",
        title_favorite.team,
        _percent(title_favorite.title_probability),
    )
    columns[1].metric(
        "Champions League",
        champions_favorite.team,
        _percent(
            champions_favorite.qualification_probabilities.get(
                "champions_league", 0.0
            )
        ),
    )
    columns[2].metric(
        "Relegation risk",
        relegation_favorite.team,
        _percent(relegation_favorite.relegation_probability),
    )
    columns[3].metric("Remaining matches", str(run.forecast.remaining_fixtures))

    st.subheader("Projected table")
    display = table.copy()
    display["Projected Pts"] = display["Projected Pts"].round(1)
    display["Projected Pos"] = display["Projected Pos"].round(1)
    for column in ("Title", "Champions League", "Relegation"):
        display[column] = display[column].map(_percent)
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.subheader("Title race")
    title = table[["Team", "Title"]].set_index("Team")
    st.bar_chart(title)

    selected = st.selectbox("Team deep dive", table["Team"], key="domestic_team")
    team = run.forecast.teams[selected]
    deep_dive = pd.DataFrame(
        {
            "Position": range(1, run.forecast.team_count + 1),
            "Probability": team.position_probabilities,
        }
    ).set_index("Position")
    st.bar_chart(deep_dive)


def _fixture_label(row: Any) -> str:
    date = pd.Timestamp(row.date).strftime("%d %b")
    return f"{date} · {row.home_team} vs {row.away_team}"


def _scheduled(run: ForecastRun) -> pd.DataFrame:
    return run.matches[
        run.matches["home_goals"].isna() & run.matches["away_goals"].isna()
    ].sort_values("date")


def _render_fixtures(run: ForecastRun) -> None:
    fixtures = _scheduled(run).copy()
    if fixtures.empty:
        st.info("There are no remaining fixtures in the current data snapshot.")
        return
    fixtures["Date"] = pd.to_datetime(fixtures["date"]).dt.strftime("%d %b %Y")
    display = fixtures.rename(
        columns={"home_team": "Home", "away_team": "Away", "status": "Status"}
    )[["Date", "Home", "Away", "Status"]]
    st.dataframe(display, use_container_width=True, hide_index=True)


def _render_breakdown(run: ForecastRun) -> None:
    fixtures = _scheduled(run)
    if fixtures.empty:
        st.info("There are no remaining fixtures to preview.")
        return
    records = list(fixtures.itertuples(index=False))
    selected_index = st.selectbox(
        "Fixture",
        range(len(records)),
        format_func=lambda index: _fixture_label(records[index]),
        key="domestic_fixture",
    )
    fixture = records[selected_index]
    lookup = {
        (item.home_team, item.away_team): item for item in run.breakdowns
    }
    breakdown = lookup[(fixture.home_team, fixture.away_team)]

    st.subheader(f"{breakdown.home_team} vs {breakdown.away_team}")
    outcome_columns = st.columns(3)
    outcome_columns[0].metric("Home win", _percent(breakdown.probabilities["home_win"]))
    outcome_columns[1].metric("Draw", _percent(breakdown.probabilities["draw"]))
    outcome_columns[2].metric("Away win", _percent(breakdown.probabilities["away_win"]))

    goal_columns = st.columns(4)
    goal_columns[0].metric("Home xG", f"{breakdown.expected_goals['home']:.2f}")
    goal_columns[1].metric("Away xG", f"{breakdown.expected_goals['away']:.2f}")
    goal_columns[2].metric(
        "Over 2.5",
        _percent(breakdown.goal_markets["over_under_2_5"]["over"]),
    )
    goal_columns[3].metric(
        "Both score",
        _percent(breakdown.goal_markets["both_teams_to_score"]["yes"]),
    )

    left, right = st.columns(2)
    with left:
        st.markdown("#### Most likely scorelines")
        scorelines = pd.DataFrame(breakdown.top_scorelines)[
            ["score", "probability"]
        ].rename(columns={"score": "Score", "probability": "Probability"})
        scorelines["Probability"] = scorelines["Probability"].map(_percent)
        st.dataframe(scorelines, use_container_width=True, hide_index=True)
    with right:
        st.markdown("#### Model comparison")
        comparison = []
        for name, values in breakdown.model_comparison.items():
            probabilities = values["probabilities"]
            comparison.append(
                {
                    "Model": MODEL_LABELS.get(name, name.replace("_", " ").title()),
                    "Home": _percent(probabilities["home_win"]),
                    "Draw": _percent(probabilities["draw"]),
                    "Away": _percent(probabilities["away_win"]),
                }
            )
        st.dataframe(pd.DataFrame(comparison), use_container_width=True, hide_index=True)

    if st.button("Calculate season impact", type="primary"):
        with st.spinner("Conditioning the season on each match result..."):
            impact = build_breakdown_with_impact(
                run,
                fixture,
                n_simulations=400,
            )
        st.session_state["domestic_impact"] = (
            run.config.slug,
            fixture.home_team,
            fixture.away_team,
            impact,
        )
    state = st.session_state.get("domestic_impact")
    if state and state[:3] == (
        run.config.slug,
        fixture.home_team,
        fixture.away_team,
    ):
        _render_impact(state[3])


def _render_impact(breakdown: Any) -> None:
    st.markdown("#### Season impact by result")
    rows = []
    for team, impact in (breakdown.season_impact or {}).items():
        for outcome, metrics in impact["outcomes"].items():
            rows.append(
                {
                    "Team": team,
                    "Result": outcome.replace("_", " ").title(),
                    "Title": _percent(metrics.get("title_probability", 0.0)),
                    "Europe": _percent(metrics.get("europe_probability", 0.0)),
                    "Relegation": _percent(metrics.get("relegation_probability", 0.0)),
                    "Expected Pts": round(metrics.get("expected_points", 0.0), 1),
                }
            )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_validation(run: ForecastRun) -> None:
    if run.validation.empty:
        st.info("Enable rolling validation in the sidebar and run the forecast again.")
        return
    display = run.validation[
        ["model", "logloss", "brier", "rps", "calibration_error", "n_predictions"]
    ].copy()
    display = display.rename(
        columns={
            "model": "Model",
            "logloss": "Log loss",
            "brier": "Brier",
            "rps": "RPS",
            "calibration_error": "Calibration error",
            "n_predictions": "Matches",
        }
    )
    for column in ("Log loss", "Brier", "RPS", "Calibration error"):
        display[column] = display[column].round(4)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.caption(
        "Lower is better. Each prediction is fitted only on matches completed before it."
    )


def render_domestic_leagues() -> None:
    leagues = list_leagues()
    names = {config.name: config for config in leagues}
    with st.sidebar:
        st.header("Domestic forecast")
        league_name = st.selectbox("League", list(names), key="domestic_league")
        model_options = ["auto", *MODEL_NAMES]
        model = st.selectbox(
            "Match model",
            model_options,
            format_func=lambda value: MODEL_LABELS[value],
            key="domestic_model",
        )
        simulations = int(
            st.number_input(
                "Simulations",
                min_value=250,
                max_value=20_000,
                value=2_000,
                step=250,
                key="domestic_simulations",
            )
        )
        validate = st.checkbox("Run rolling validation", value=True)
        run_clicked = st.button("Run league forecast", type="primary")

    config = names[league_name]
    selection = (config.slug, model, simulations, validate)
    if run_clicked:
        run = _cached_forecast(*selection)
        st.session_state["domestic_run"] = (selection, run)

    state = st.session_state.get("domestic_run")
    st.title(f"{config.name} 2026/27")
    st.caption(
        "Scoreline models, rolling validation and Monte Carlo season forecasts."
    )
    if not state or state[0] != selection:
        st.info("Choose the settings in the sidebar and run the league forecast.")
        return

    run = state[1]
    st.caption(
        f"Model: {MODEL_LABELS.get(run.selected_model, run.selected_model)} · "
        f"{run.forecast.simulations:,} simulations · generated {run.generated_at[:19]} UTC"
    )
    overview, fixtures, breakdown, validation = st.tabs(
        ["Season forecast", "Fixtures", "Match breakdown", "Validation"]
    )
    with overview:
        _render_overview(run)
    with fixtures:
        _render_fixtures(run)
    with breakdown:
        _render_breakdown(run)
    with validation:
        _render_validation(run)


__all__ = ["render_domestic_leagues"]
