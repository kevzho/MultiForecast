import math
import os 
import json
import pandas as pd

#basic elo math measuring skill relative to the pool of players, with a scaling factor of 400 (common in chess, applying here)
def expected_score(team_a_elo, team_b_elo):
    return 1 / (1 + math.pow(10, (team_b_elo - team_a_elo) / 400))

#deciding match score, where 1 is a win and 0.5 is a draw
def match_score(hg, ag):
    if hg > ag:
        return 1.0, 0.0
    elif hg < ag:
        return 0.0, 1.0
    else:
        return 0.5, 0.5

#updating elos based on the match results 
#with kfactor of 20 (common in chess with FIDE ratings under 2400, may adjust due to prem being less volatile than chess ratings)
def update_elo(rating_h, rating_a, hg, ag, k=20, home_adv = 80):
    #adjusing home rating with home advantage, proven in /notebook-viz/match-level-eda.ipynb
    rating_h_adj = rating_h + home_adv

    #find expected score of home and away teams based on their ratings
    exp_h = expected_score(rating_h_adj, rating_a)
    exp_a = 1 - exp_h

    #run match score
    score_h, score_a = match_score(hg, ag)

    #adjust new ratings based on how much the actual score deviates from the expected score, scaled by k
    #Is this how njsports.com does it? lol
    new_rating_h = rating_h + k * (score_h - exp_h)
    new_rating_a = rating_a + k * (score_a - exp_a)
    new_rating_h = round(new_rating_h, 1)
    new_rating_a = round(new_rating_a, 1)

    return new_rating_h, new_rating_a


#runs processed matches in order, producing ratings for all teams (at current time)
def compute_elo(df, k=20, home_adv=80, base_rating=1500):
    teams = set(df["HomeTeam"]).union(df["AwayTeam"])
    ratings = {team: base_rating for team in teams}

    df = df.sort_values("Date")

    #iterating through matches in order, updating ratings after each match
    for _, row in df.iterrows():
        home = row["HomeTeam"]
        away = row["AwayTeam"]
        hg = row["FTHG"]
        ag = row["FTAG"]

        #checking for null values
        if pd.isna(hg) or pd.isna(ag):
            continue

        #get current ratings and update elo based on match result
        r_home, r_away = ratings[home], ratings[away]
        new_home, new_away = update_elo(
            r_home, r_away, hg, ag, k, home_adv
        )

        ratings[home] = new_home
        ratings[away] = new_away

    return ratings

#cacheing ratings to json
def save_elo(ratings, season_code="2526"):
    """
    Saves Elo ratings as JSON in the data/ folder.
    """
    path = f"cache/elo_ratings_{season_code}.json"
    os.makedirs("cache", exist_ok=True)

    with open(path, "w") as f:
        json.dump(ratings, f, indent=2)

#saves elo as csv
def save_elo_csv(ratings, season_code="2526"):
    """
    Saves Elo ratings as CSV in the data/ folder.
    """
    os.makedirs("data", exist_ok=True)
    elo_df = pd.DataFrame(list(ratings.items()), columns=["Team", "EloRating"])
    elo_df = elo_df.sort_values("EloRating", ascending=False)
    csv_path = f"data/elo_ratings_{season_code}.csv"
    elo_df.to_csv(csv_path, index=False)

#draw_rate proven in notebook-viz/match-level-eda.ipynb to be around 0.2652, can adjust
def elo_to_match_probs(rating_h, rating_a, home_adv=80, draw_rate = 0.2652):
    rating_h_adj = rating_h + home_adv
    exp_h = expected_score(rating_h_adj, rating_a)
    exp_a = 1 - exp_h

    #setting draw probability based on parameter
    draw_prob = draw_rate
    win_prob_h = exp_h * (1 - draw_prob)
    win_prob_a = exp_a * (1 - draw_prob)

    return win_prob_h, draw_prob, win_prob_a

#computing elos and table state for curr league
def compute_table_state(df, k=20, home_adv=80, base_rating=1500):
    """
    Returns:
        ratings: final Elo ratings after all played matches (not including future matches)
        table: current points per team
    """
    ratings = compute_elo(df, k, home_adv, base_rating)
    table = {team: 0 for team in ratings.keys()}

    for _, row in df.iterrows():
        home, away = row["HomeTeam"], row["AwayTeam"]
        hg, ag = row["FTHG"], row["FTAG"]
        if pd.isna(hg) or pd.isna(ag):
            continue
        if hg > ag:
            table[home] += 3
        elif hg < ag:
            table[away] += 3
        else:
            table[home] += 1
            table[away] += 1

    return ratings, table
