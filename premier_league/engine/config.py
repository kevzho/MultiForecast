from pathlib import Path

import pandas as pd

#parameters
SEASON = "2627"
LEAGUE = "E0"

ELO_K = 20
HOME_ADV = 100
BASE_RATING = 1500

ACTIVE_TEAMS_2627 = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton",
    "Chelsea", "Coventry City", "Crystal Palace", "Everton", "Fulham",
    "Hull City", "Ipswich Town", "Leeds", "Liverpool", "Man City",
    "Man United", "Newcastle", "Nott'm Forest", "Sunderland", "Tottenham",
]

# 2026/27 promoted-team Elo seeds:
# Tottenham are the lowest-rated returning PL side in the final 2025/26 Elo table
# (1452.7). Promoted teams start just below that anchor, ordered by promotion:
# Coventry (Championship winners), Ipswich (2nd), Hull (playoff/6th).
PROMOTED_ELO_SEEDS_2627 = {
    "Coventry City": 1448.0,
    "Ipswich Town": 1442.0,
    "Hull City": 1436.0,
}
def _draw_rate_from_current_data(default=0.2652):
    data_path = Path(__file__).resolve().parents[2] / "data" / f"E0_{SEASON}.csv"
    if not data_path.exists():
        return default
    df = pd.read_csv(data_path)
    played = df.dropna(subset=["FTHG", "FTAG"])
    if played.empty:
        return default
    return float((played["FTHG"] == played["FTAG"]).mean())


DRAW_RATE = _draw_rate_from_current_data()
N_SIMULATIONS = 20000
