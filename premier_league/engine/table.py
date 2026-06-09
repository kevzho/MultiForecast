from pathlib import Path
from scipy.stats import zscore, percentileofscore
import pandas as pd


SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parents[1]
DATA_DIR = PROJECT_ROOT / "data"

MATCHES_PATH = DATA_DIR / "E0_2526.csv"
OUTPUT_PATH = DATA_DIR / "summary_table2526.csv"


def initialize_table(teams):
    table = {}

    for team in teams:
        table[team] = {
            "points": 0,
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "gf": 0,
            "ga": 0,
            "gd": 0,
            "last5": []
        }

    return table


def update_actual_table(table, home, away, home_goals, away_goals, result):
    table[home]["played"] += 1
    table[away]["played"] += 1

    table[home]["gf"] += home_goals
    table[home]["ga"] += away_goals
    table[away]["gf"] += away_goals
    table[away]["ga"] += home_goals

    if result == "H":
        table[home]["points"] += 3
        table[home]["wins"] += 1
        table[away]["losses"] += 1
        table[home]["last5"].append("W")
        table[away]["last5"].append("L")

    elif result == "D":
        table[home]["points"] += 1
        table[away]["points"] += 1
        table[home]["draws"] += 1
        table[away]["draws"] += 1
        table[home]["last5"].append("D")
        table[away]["last5"].append("D")

    else:
        table[away]["points"] += 3
        table[away]["wins"] += 1
        table[home]["losses"] += 1
        table[away]["last5"].append("W")
        table[home]["last5"].append("L")

    table[home]["last5"] = table[home]["last5"][-5:]
    table[away]["last5"] = table[away]["last5"][-5:]

    table[home]["gd"] = table[home]["gf"] - table[home]["ga"]
    table[away]["gd"] = table[away]["gf"] - table[away]["ga"]


def update_simulation_table(table, home, away, result):
    table[home]["played"] += 1
    table[away]["played"] += 1

    if result == "H":
        table[home]["points"] += 3
        table[home]["wins"] += 1
        table[away]["losses"] += 1
    elif result == "D":
        table[home]["points"] += 1
        table[away]["points"] += 1
        table[home]["draws"] += 1
        table[away]["draws"] += 1
    else:
        table[away]["points"] += 3
        table[away]["wins"] += 1
        table[home]["losses"] += 1


def rank_actual_table(table):
    return sorted(
        table.items(),
        key=lambda x: (x[1]["points"], x[1]["gd"], x[1]["gf"]),
        reverse=True
    )


def rank_simulation_table(table):
    return sorted(
        table.items(),
        key=lambda x: x[1]["points"],
        reverse=True
    )


def classify_strength(z):
    if z >= 1:
        return "Strong"
    elif 0 <= z < 1:
        return "Above Average"
    elif -1 < z < 0:
        return "Average"
    else:
        return "Weak"


def build_summary_table():
    raw_matches = pd.read_csv(MATCHES_PATH)

    teams = sorted(set(raw_matches["HomeTeam"]).union(set(raw_matches["AwayTeam"])))
    table = initialize_table(teams)

    for _, row in raw_matches.iterrows():
        update_actual_table(
            table,
            row["HomeTeam"],
            row["AwayTeam"],
            int(row["FTHG"]),
            int(row["FTAG"]),
            row["FTR"]
        )

    ranked = rank_actual_table(table)

    rows = []
    for pos, (team, stats) in enumerate(ranked, start=1):
        rows.append({
            "Pos": pos,
            "Team": team,
            "MP": stats["played"],
            "W": stats["wins"],
            "D": stats["draws"],
            "L": stats["losses"],
            "GF": stats["gf"],
            "GA": stats["ga"],
            "GD": stats["gd"],
            "Pts": stats["points"],
            "Last5": stats["last5"]
        })

    df = pd.DataFrame(rows)

    df["Pts_zscore"] = zscore(df["Pts"]).round(2)
    df["GD_zscore"] = zscore(df["GD"]).round(2)
    df["Pts_pct"] = df["Pts"].apply(lambda x: percentileofscore(df["Pts"], x)).round(1)
    df["GD_pct"] = df["GD"].apply(lambda x: percentileofscore(df["GD"], x)).round(1)
    df["Strength"] = df["Pts_zscore"].apply(classify_strength)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved summary table to {OUTPUT_PATH}")
    return df


if __name__ == "__main__":
    summary = build_summary_table()
    print(summary)
