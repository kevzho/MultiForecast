import streamlit as st

from domestic.ui import render_domestic_leagues
from worldcup.ui import render_worldcup_tab


st.set_page_config(
    page_title="MultiForecast — World Cup & Big Five Leagues",
    page_icon="⚽",
    layout="wide",
)

tab_wc, tab_domestic = st.tabs(["World Cup 2026", "Big Five Leagues"])

with tab_wc:
    render_worldcup_tab()

with tab_domestic:
    render_domestic_leagues()
