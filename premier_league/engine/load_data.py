#translate raw data into interpretable format for analysis

import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

REQUIRED_COLS = [
    "Date",
    "HomeTeam",
    "AwayTeam",
    "FTHG",
    "FTAG"
]

def load_season_df(season_code="2526", league="E0"):
    path = os.path.join(DATA_DIR, f"{league}_{season_code}.csv")
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df[REQUIRED_COLS].copy()
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")

    return df

def split_played_future(df):
    played = df.dropna(subset=["FTHG", "FTAG"])
    future = df[df["FTHG"].isna() & df["FTAG"].isna()] #checking for rows with null full time hg and ag (indicating non-played status)
    return played, future

def load_power_rankings(season="2526"):
    """Load Elo ratings from power_rankings CSV"""
    path = os.path.join(DATA_DIR, f"power_rankings_{season}.csv")
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"Cannot find: {path}")
    
    df = pd.read_csv(path)
    df["Team"] = df["Team"].str.strip()
    
    ratings = dict(zip(df["Team"], df["EloRating"]))
    return ratings


def load_current_table(season="2526"):
    """Load current league standings from summary_table CSV"""
    path = os.path.join(DATA_DIR, f"summary_table{season}.csv")
    
    if not os.path.exists(path):
        raise FileNotFoundError(f"Cannot find: {path}")
    
    df = pd.read_csv(path)
    df["Team"] = df["Team"].str.strip()
    
    table = {}
    for _, row in df.iterrows():
        table[row["Team"]] = {
            "points": row["Pts"],
            "played": row["MP"],
            "wins": row["W"],
            "draws": row["D"],
            "losses": row["L"]
        }
    
    return table
