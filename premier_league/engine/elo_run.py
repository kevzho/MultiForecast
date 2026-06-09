from .elo import compute_table_state, save_elo, save_elo_csv
import pandas as pd
import os

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]


def main():
    csv_path = BASE_DIR / "data" / "E0_2526.csv"
    df = pd.read_csv(csv_path)

    ratings, table = compute_table_state(df) #defaulted to k=20, home_adv=80, base_rating=1500

    elo_df = pd.DataFrame(list(ratings.items()), columns=["Team", "EloRating"])

    #sort values by elo (descending) to get current league table order, or even just power rankings
    power_rankings_df = elo_df.sort_values("EloRating", ascending=False).reset_index(drop=True)
    power_rankings_df["Rank "] = power_rankings_df.index + 1

    os.makedirs("data", exist_ok=True)

    output_path_elo = BASE_DIR / "data" / "elo_ratings_2526.csv"
    output_path_power = BASE_DIR / "data" / "power_rankings_2526.csv"

    elo_df.to_csv(output_path_elo, index=False)
    power_rankings_df.to_csv(output_path_power, index=False)
    save_elo(ratings, season_code="2526")

    print(f"Elo ratings saved to /data folder.")


if __name__ == "__main__":
    main()
