#core monte-carlo engine
from tqdm import tqdm
import random
from copy import deepcopy

from premier_league.engine.elo import elo_to_match_probs
from .table import initialize_table, rank_simulation_table, update_simulation_table
from premier_league.engine.team_names import normalize_team

def sample_match(win_h, draw, win_a):
    r = random.random()
    if r < win_h:
        return "H"
    elif r < win_h + draw:
        return "D"
    else:
        return "A"
    
def simulate_season(
    fixtures_df, ratings, current_table, n_sims, home_adv, draw_rate
):
    #get all of the teams in current table
    teams = list(current_table.keys())

    #initialize counts for titles and top 4 finishes
    title_counts = {team: 0 for team in teams}
    top4_counts = {team: 0 for team in teams}

    #initialize relegation, position, and total points counts for all teams
    relegation_counts = {team: 0 for team in teams}
    position_counts = {team: [0]*20 for team in teams}
    total_points = {team: 0 for team in teams}

    #iterate through # of simulations
    for n in tqdm(range(n_sims), desc="Simulating seasons"):
        #make copy of current table to update during simulation
        table_copy = deepcopy(current_table)

        #go through every row in fixtures dataframe
        for _, row in fixtures_df.iterrows():
            home_raw = row["HomeTeam"]
            away_raw = row["AwayTeam"]
            home = normalize_team(home_raw)
            away = normalize_team(away_raw)

            if home not in ratings or away not in ratings:
                missing = [t for t in (home, away) if t not in ratings]
                raise KeyError(
                    f"Missing Elo rating(s) for {missing}. "
                    f"Fixture raw values: {home_raw!r} vs {away_raw!r}"
                )

            #get match probabilities based on current elo ratings
            win_h, draw, win_a = elo_to_match_probs(
                ratings[home],
                ratings[away],
                home_adv,
                draw_rate
            )

            #simulate sample match result
            result = sample_match(win_h, draw, win_a)
            #update table based off of that match result
            update_simulation_table(table_copy, home, away, result)

        final_table = rank_simulation_table(table_copy)
        if n == 1:
            print(final_table)

        #Find the winner of the premier league in this simulation
        champion = final_table[0][0]
        title_counts[champion] += 1

        #find team in each position
        for pos, (team, stats) in enumerate(final_table):
            position_counts[team][pos] += 1
            total_points[team] += stats["points"]

            if pos < 4:
                top4_counts[team] += 1
            if pos >= 17:
                relegation_counts[team] += 1

    #convert all of the counts into probabilities and expected points
    results = {}

    for team in teams:
        #expected value for title probability, top 4 probability, relegation probability, expected points, and position distribution
        results[team] = {
            "title_prob": title_counts[team] / n_sims,
            "top4_prob": top4_counts[team] / n_sims,
            "relegation_prob": relegation_counts[team] / n_sims,
            "expected_points": total_points[team] / n_sims,
            "position_distribution": [
                count / n_sims for count in position_counts[team]
            ]
        }

    return results
