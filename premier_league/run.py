from premier_league.engine.load_data import load_power_rankings, load_current_table
from premier_league.engine.config import SEASON
from premier_league.engine.pipeline import run_simulation_pipeline
from premier_league.engine.remaining_fixtures import get_remaining_fixtures

import pandas as pd
import os
from pathlib import Path


def main(force_refresh=False):
    print("Starting Premier League simulation...")
    
    #specify season
    season = SEASON
    
    #Loading power rankings and current table
    print("Loading power rankings...")
    ratings = load_power_rankings(season)
    print(f"   Loaded ratings for {len(ratings)} teams")
    
    print("Loading current table...")
    current_table = load_current_table(season)
    print(f"   Current table: {len(current_table)} teams")
    
    #Loading remaining fixtures
    print("Loading fixtures...")
    fixtures_df = get_remaining_fixtures()
    print(f"   Loaded {len(fixtures_df)} remaining fixtures")
    print(f"   Date range: {fixtures_df['Date'].min()} to {fixtures_df['Date'].max()}")
    
    #running sim
    print("Running Monte Carlo simulation (this may take a minute)...")
    print("   This runs 10,000+ simulations of the remaining season")
    
    results = run_simulation_pipeline(
        fixtures_df,
        ratings,
        current_table,
        season=season
    )
    
    # 4. Display results
    print("\n" + "="*60)
    print("SIMULATION COMPLETE")
    print("="*60 + "\n")
    
    results_df = pd.DataFrame(results)
    print(f"Top teams after simulation:")

    if results_df is not None and not results_df.empty:
        print(results_df.head(10))  #show top 10 teams
    else:
        print("No results returned from simulation pipeline")
    
    # Optional: Save results
    output_path = f"data/simulation_results_{season}.csv"
    results_df.to_csv(output_path)
    print(f"\nResults saved to {output_path}")

if __name__ == "__main__":
    #set force_refresh=True to bypass cache and get fresh data - set to true when matchweek changes
    main(force_refresh=True)
    