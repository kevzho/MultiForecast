#import all parameters in our config.py file
from premier_league.engine.config import (
    HOME_ADV,
    DRAW_RATE,
    N_SIMULATIONS,
    SEASON,
)

from premier_league.engine.simulation import simulate_season
from premier_league.engine.cache_utils import save_json, load_json


def run_simulation_pipeline(
    fixtures_df,
    ratings,
    current_table,
    season=SEASON
):

    #define cache path for simulations
    cache_path = f"cache/simulations_{season}.json"

    #load cached if there is cached
    cached = load_json(cache_path)
    if cached:
        print("Loading cached simulations...")
        return cached

    print("Running simulations...")

    #simulate season, function from simulation.py
    results = simulate_season(
        fixtures_df=fixtures_df,
        ratings=ratings,
        current_table=current_table,
        n_sims=N_SIMULATIONS,
        home_adv=HOME_ADV,
        draw_rate=DRAW_RATE
    )

    #save results in json
    save_json(results, cache_path)

    return results
