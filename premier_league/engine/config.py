from pathlib import Path

import pandas as pd

#parameters
SEASON = "2526"
LEAGUE = "E0"

ELO_K = 20
HOME_ADV = 100
BASE_RATING = 1500
def _draw_rate_from_current_data(default=0.2652):
    data_path = Path(__file__).resolve().parents[2] / "data" / "E0_2526.csv"
    if not data_path.exists():
        return default
    df = pd.read_csv(data_path)
    played = df.dropna(subset=["FTHG", "FTAG"])
    if played.empty:
        return default
    return float((played["FTHG"] == played["FTAG"]).mean())


DRAW_RATE = _draw_rate_from_current_data()
N_SIMULATIONS = 20000
