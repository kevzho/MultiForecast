import streamlit as st

from premier_league.dashboard import render_premier_league
from worldcup.ui import render_worldcup_tab


st.set_page_config(
    page_title="MultiForecast — Premier League & World Cup",
    page_icon="⚽",
    layout="wide",
)

tab_pl, tab_wc = st.tabs(["Premier League", "World Cup 2026"])

with tab_pl:
    render_premier_league()

with tab_wc:
    render_worldcup_tab()
