import pandas as pd
import ast
from premier_league.engine.config import N_SIMULATIONS
import logging
import unicodedata

#for loggin & debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_team_name(name):
    """Remove/clean special characters from team names"""
    #Normalize unicode characters
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    #remove any ASCII characters
    name = ''.join(char for char in name if ord(char) < 128)
    #special cases
    name = name.replace("'", "").replace('"', '')
    return name.strip()

# Then in load_simulation_data(), after getting teams:

from premier_league.engine.config import SEASON


def load_simulation_data(csv_path=f"data/simulation_results_{SEASON}.csv"):
    """
    Load the CSV and convert string arrays to actual lists
    """
    #log 
    logger.info("Loading simulation data from CSV: %s", csv_path)

    df = pd.read_csv(csv_path, index_col=0)
    
    #find teams (from columns)
    teams = df.columns.tolist()
    
    #process position data
    original_teams = df.columns.tolist()
    
    # Create mapping from cleaned names to original names
    team_mapping = {}
    cleaned_teams = []
    for team in original_teams:
        cleaned = clean_team_name(team)
        team_mapping[cleaned] = team  # Map cleaned -> original
        cleaned_teams.append(cleaned)
    
    logger.info(f"Found {len(cleaned_teams)} teams")
    
    # Process position data
    position_data = {}
    for cleaned_team, original_team in zip(cleaned_teams, original_teams):
        # Use ORIGINAL team name to access dataframe
        pos_str = df.loc['position_distribution', original_team]
        try:
            # Parse the string into a list of floats
            position_data[cleaned_team] = ast.literal_eval(pos_str)
        except (SyntaxError, ValueError) as e:
            logger.error(f"Failed to parse position data for {cleaned_team}: {e}")
            # Provide empty list as fallback
            position_data[cleaned_team] = [0.0] * 20
    
    # Create clean data structure
    results = {
        'teams': cleaned_teams,
        'original_team_mapping': team_mapping,  # Useful for debugging
        'title_prob': {},
        'top4_prob': {},
        'relegation_prob': {},
        'expected_points': {},
        'position_distribution': position_data,
        'metadata': {
            'timestamp': pd.Timestamp.now().isoformat(),
            'num_simulations': N_SIMULATIONS,
            'source_file': csv_path
        }
    }
    
    # Fill in probabilities and expected points
    for cleaned_team, original_team in zip(cleaned_teams, original_teams):
        try:
            results['title_prob'][cleaned_team] = float(df.loc['title_prob', original_team])
            if cleaned_team == "Arsenal":
                logger.info(f"Arsenal title_prob loaded as {results['title_prob'][cleaned_team]}")
            results['top4_prob'][cleaned_team] = float(df.loc['top4_prob', original_team])
            results['relegation_prob'][cleaned_team] = float(df.loc['relegation_prob', original_team])
            results['expected_points'][cleaned_team] = float(df.loc['expected_points', original_team])
        except KeyError as e:
            logger.error(f"Missing data for {cleaned_team}: {e}")
            # Set defaults
            results['title_prob'][cleaned_team] = 0.0
            results['top4_prob'][cleaned_team] = 0.0
            results['relegation_prob'][cleaned_team] = 0.0
            results['expected_points'][cleaned_team] = 0.0
    
    # Validate data
    logger.info(f"✅ Loaded data for {len(results['teams'])} teams")
    logger.info(f"Title probability sum: {sum(results['title_prob'].values()):.2f}")

    return results

def format_probability(p):
    """Conversion to percentage string with one decimal place"""
    return f"{p*100:.1f}%"

def get_top_teams(data, metric='title_prob', n=5):
    """Get top n teams by a metric"""
    teams = data['teams']
    values = [(team, data[metric][team]) for team in teams]
    sorted_teams = sorted(values, key=lambda x: x[1], reverse=True)
    return sorted_teams[:n]

def get_bottom_teams(data, metric='relegation_prob', n=5):
    """Get bottom n teams by a metric"""
    teams = data['teams']
    values = [(team, data[metric][team]) for team in teams]
    sorted_teams = sorted(values, key=lambda x: x[1], reverse=True)
    return sorted_teams[:n]