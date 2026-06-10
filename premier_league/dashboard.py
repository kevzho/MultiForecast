#Streamlit dashboard
#importing necessary libraries
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from premier_league.engine.config import N_SIMULATIONS, SEASON

#import modules
from premier_league.data_processor import load_simulation_data, format_probability, get_top_teams, get_bottom_teams
from premier_league.cache_manager import load_simulation_results, save_simulation_results, clear_cache, get_cache_key


def render_premier_league():
    # Title
    st.title(f"Premier League Season Simulator: Predicting the 20{SEASON[:2]}/{SEASON[2:]} Season")
    st.markdown("(A Monte Carlo simulation of remaining fixtures).")

    #sidebar for controls (left)
    with st.sidebar:
        st.header("Controls")
        
        #create cache status
        st.subheader("Cache")
        
        #attempt to load cached data first
        cache_key = get_cache_key(
            data_source=SEASON,
            params={"num_simulations": N_SIMULATIONS}
        )

        cached_data = load_simulation_results(cache_key=cache_key)
        
        if cached_data:
            st.success(f"✔ Loaded from cache")
            st.caption(f"Cached at: {cached_data['metadata']['timestamp']}")
            data = cached_data
        else:
            st.warning("⚠ No cache found, loading from CSV")
            #load from csv using function
            data = load_simulation_data()
            #save to cache
            cache_key = get_cache_key(
                data_source=SEASON,
                params={"num_simulations": data['metadata']['num_simulations']}
            )

            # Save to cache
            save_simulation_results(data, cache_key=cache_key)
                
        #refresh button enforcing cache clear & rerun
        if st.button("⟳ Force Refresh"):
            clear_cache()
            st.rerun()
        
        #simulation info
        st.divider()
        st.subheader("Simulation Info")
        st.metric("Teams", len(data['teams']))
        st.metric("Simulations", f"{data['metadata']['num_simulations']:,}")
        st.caption(f"Last updated: {data['metadata']['timestamp'][:10]}")

    #Main content area (right)
    st.header("Key Probabilities")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        top_title = get_top_teams(data, 'title_prob', 1)[0]
        st.metric(
            "Title Favorite",
            top_title[0],
            format_probability(top_title[1])
        )

    with col2:
        top4_leader = get_top_teams(data, 'top4_prob', 1)[0]
        st.metric(
            "Most Likely Top 4",
            top4_leader[0],
            format_probability(top4_leader[1])
        )

    with col3:
        relegation_leader = get_bottom_teams(data, 'relegation_prob', 1)[0]
        st.metric(
            "Most Likely Relegated",
            relegation_leader[0],
            format_probability(relegation_leader[1])
        )

    with col4:
        top_points = get_top_teams(data, 'expected_points', 1)[0]
        st.metric(
            "Expected Points Leader",
            top_points[0],
            f"{top_points[1]:.1f}"
        )

    #Title race section
    st.header("Title Race")

    title_data = pd.DataFrame([
        {"Team": team, "Probability": data['title_prob'][team]}
        for team in data['teams']
    ]).sort_values("Probability", ascending=False)

    fig = px.bar(
        title_data[title_data['Probability'] > 0.01],
        y="Team",
        x="Probability",
        title="Premier League Title Probability",
        color="Probability",
        color_continuous_scale="Viridis",
        text_auto='.1%',
        orientation='h' #horizontal orientation for better readability
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"), 
        height=400,
        margin=dict(l=120, r=20, t=40, b=20),
        xaxis_title="Probability",
        yaxis_title=""
    )
    st.plotly_chart(fig, use_container_width=True)

    #Top 4 and relegation in two columns side-by-side
    col1, col2 = st.columns(2)

    with col1:
        st.header("Top 4 Probability")
        top4_data = pd.DataFrame([
            {"Team": team, "Probability": data['top4_prob'][team]}
            for team in data['teams']
        ]).sort_values("Probability", ascending=False)
        
        fig = px.bar(
            top4_data.head(10),
            y="Team",
            x="Probability",
            title="Top 10 - Champions League Probability",
            color="Probability",
            color_continuous_scale="Blues",
            text_auto='.1%',
            orientation='h'
        )
        fig.update_layout(
            yaxis=dict(autorange="reversed"),
            height=400,
            margin=dict(l=120, r=20, t=40, b=20),
            xaxis_title="Probability",
            yaxis_title=""
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.header("Relegation Battle")
        rel_data = pd.DataFrame([
            {"Team": team, "Probability": data['relegation_prob'][team]}
            for team in data['teams']
        ]).sort_values("Probability", ascending=False)
        
        fig = px.bar(
            rel_data[rel_data['Probability'] > 0.01],
            y="Team",
            x="Probability",
            title="Teams with >1% Relegation Chance",
            color="Probability",
            color_continuous_scale="Reds",
            text_auto='.1%',
            orientation='h'
        )
        fig.update_layout(
            yaxis=dict(autorange="reversed"),
            height=max(300, len(rel_data[rel_data['Probability'] > 0.01]) * 35), 
            margin=dict(l=120, r=20, t=40, b=20),
            xaxis_title="Probability",
            yaxis_title=""
        )
        st.plotly_chart(fig, use_container_width=True)

    #Expected # of points
    st.header("Expected Points Table")

    points_data = pd.DataFrame([
        {"Team": team, "Expected Points": data['expected_points'][team]}
        for team in data['teams']
    ]).sort_values("Expected Points", ascending=False)

    fig = px.bar(
        points_data,
        y="Team",
        x="Expected Points",
        title="Expected Final Points (note: not actual points and will most certainly be different)",
        color="Expected Points",
        color_continuous_scale="Greens",
        orientation='h' 
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
        height=600,  # Taller for 20 teams
        margin=dict(l=120, r=20, t=40, b=20),
        xaxis_title="Expected Points",
        yaxis_title=""
    )
    st.plotly_chart(fig, use_container_width=True)

    #Position Distribution Heatmap
    st.header("Position Distribution Heatmap")

    #Prepare data for heatmap
    pos_data = []
    for team in data['teams']:
        dist = data['position_distribution'][team]
        for pos_idx, prob in enumerate(dist):
            if prob > 0.001:  #Only show meaningful probabilities
                pos_data.append({
                    "Team": team,
                    "Position": pos_idx + 1,
                    "Probability": prob
                })

    pos_df = pd.DataFrame(pos_data)
    pivot_df = pos_df.pivot(index="Team", columns="Position", values="Probability").fillna(0)

    # Sort teams by most likely position
    team_order = points_data['Team'].tolist()
    pivot_df = pivot_df.reindex(team_order)

    #Create heatmap with explicit font settings
    fig = go.Figure(data=go.Heatmap(
        z=pivot_df.values,
        x=list(range(1, 21)),
        y=pivot_df.index,
        colorscale='Viridis',
        text=[[f"{val:.1%}" for val in row] for row in pivot_df.values],
        texttemplate="%{text}",
        textfont={"size": 10},
        hoverongaps=False
    ))

    fig.update_layout(
        title="Probability Heatmap of Final Positions",
        xaxis_title="Final Position",
        yaxis_title="Team",
        height=600,
        font=dict(family="Arial", size=12),
        xaxis=dict(tickmode='linear', tick0=1, dtick=1)
    )

    fig.update_yaxes(tickfont=dict(size=10))

    st.plotly_chart(fig, width='stretch')

    # Team Selector for detailed view
    st.header("Team Deep Dive")

    selected_team = st.selectbox("Select a team", data['teams'])

    if selected_team:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Title Probability",
                format_probability(data['title_prob'][selected_team])
            )
        
        with col2:
            st.metric(
                "Top 4 Probability", 
                format_probability(data['top4_prob'][selected_team])
            )
        
        with col3:
            st.metric(
                "Relegation Probability",
                format_probability(data['relegation_prob'][selected_team])
            )
        
        #position distribution for selected team
        st.subheader(f"{selected_team} - Position Distribution")
        
        pos_dist = data['position_distribution'][selected_team]
        pos_df_team = pd.DataFrame({
            "Position": list(range(1, 21)),
            "Probability": pos_dist
        })
        
        fig = px.bar(
            pos_df_team,
            x="Position",
            y="Probability",
            title=f"{selected_team} - Probability of Finishing in Each Position",
            color="Probability",
            color_continuous_scale="Plasma"
        )
        st.plotly_chart(fig, use_container_width=True)

    #footer & copyright
    st.divider()
    st.caption("Data based on ELO ratings and Monte Carlo simulation")
    st.caption("⚠ Preseason predictions require betting odds integration")
    st.caption(f"{data['metadata']['num_simulations']:,} simulations run - ©2026 Kevin Zhou")
