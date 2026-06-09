#fetches data remotely
import json
import os
import pandas as pd
import requests

from datetime import datetime

#our data directory (place `data` next to this script)
BASE_DIR = os.path.dirname(__file__)

#adjust project root
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, os.pardir, os.pardir))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

#ensure the data directory exists so writing won't raise FileNotFoundError
os.makedirs(DATA_DIR, exist_ok=True)

#fetch data we need as json and csv for caching, so we don't have to keep hitting the remote source
def csv_to_json(season_code="2526", league="E0"):
    csv_path = os.path.join(DATA_DIR, f"{league}_{season_code}.csv")
    json_path = os.path.join(DATA_DIR, f"{league}_{season_code}_raw.json")

    #checking for existing csv file 
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"{csv_path} not found. Download CSV first.")

    df = pd.read_csv(csv_path)
    #converting read csv to json for caching 
    df.to_json(json_path, orient="records", date_format="iso")

    print("Cached JSON:", json_path)

#additional helper function to get current season code (e.g. "2526" for 2025-2026 season)
def current_season_code():
    now = datetime.utcnow()
    year = now.year
    month = now.month

    if month >= 7:
        return f"{year % 100:02d}{(year + 1) % 100:02d}"
    else:
        return f"{(year - 1) % 100:02d}{year % 100:02d}"

#gets the csv from football-data.co.uk for given season and league
def download_fdc_csv(season_code = None, league = "E0"):

    #checks if we have null season code, if so default to current season code (e.g. "2526" for 2025-2026 season)
    if season_code is None:
        season_code = current_season_code()

    url = f"https://www.football-data.co.uk/mmz4281/{season_code}/{league}.csv"
    out = os.path.join(DATA_DIR, f"{league}_{season_code}.csv")
    
    print("Downloading: ", url)
    # set timeout to 10 seconds
    r = requests.get(url, timeout = 10)

    #If status code is not 200, print error (meaning that it was unsuccessful)
    if r.status_code != 200:
        print("Error: ", r.status_code)
        return 
    
    #exporting to output file
    with open(out, "wb") as f:
        f.write(r.content)
    
    print("Saved to: ", out)
    
if __name__ == "__main__":
    download_fdc_csv("2526", "E0")
    csv_to_json("2526", "E0") #downloading 25-26 premier league data
