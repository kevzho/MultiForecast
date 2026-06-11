import streamlit as st

from premier_league.dashboard import render_premier_league
from worldcup.ui import render_worldcup_tab


st.set_page_config(
    page_title="MultiForecast — World Cup 2026 & Premier League",
    page_icon="⚽",
    layout="wide",
)

tab_wc, tab_pl = st.tabs(["World Cup 2026", "Premier League 26/27"])

with tab_wc:
    render_worldcup_tab()

with tab_pl:
    render_premier_league()
