from .elo import compute_table_state, save_elo, save_elo_csv
import pandas as pd
import os

from premier_league.engine.config import PROMOTED_ELO_SEEDS_2627, SEASON

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]


def main():
    csv_path = BASE_DIR / "data" / f"E0_{SEASON}.csv"
    df = pd.read_csv(csv_path)

    if SEASON == "2627" and df[["FTHG", "FTAG"]].dropna().empty:
        previous = pd.read_csv(BASE_DIR / "data" / "power_rankings_2526.csv")
        previous_ratings = dict(zip(previous["Team"], previous["EloRating"]))
        relegated = {"West Ham", "Burnley", "Wolves"}
        ratings = {t: r for t, r in previous_ratings.items() if t not in relegated}
        ratings.update(PROMOTED_ELO_SEEDS_2627)
    else:
        ratings, table = compute_table_state(df) #defaulted to k=20, home_adv=80, base_rating=1500

    elo_df = pd.DataFrame(list(ratings.items()), columns=["Team", "EloRating"])

    #sort values by elo (descending) to get current league table order, or even just power rankings
    power_rankings_df = elo_df.sort_values("EloRating", ascending=False).reset_index(drop=True)
    power_rankings_df["Rank "] = power_rankings_df.index + 1

    os.makedirs("data", exist_ok=True)

    output_path_elo = BASE_DIR / "data" / f"elo_ratings_{SEASON}.csv"
    output_path_power = BASE_DIR / "data" / f"power_rankings_{SEASON}.csv"

    elo_df.to_csv(output_path_elo, index=False)
    power_rankings_df.to_csv(output_path_power, index=False)
    save_elo(ratings, season_code=SEASON)

    print(f"Elo ratings saved to /data folder.")


if __name__ == "__main__":
    main()
