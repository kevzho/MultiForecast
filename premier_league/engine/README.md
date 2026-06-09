# Premier League Engine

- **`config.py`** - Central configuration file storing simulation parameters (number of simulations, data paths, cache settings)
- **`elo.py`** - Implements the ELO rating system logic (calculations, updates, home advantage)
- **`elo_run.py`** - Executes the ELO rating pipeline to generate current team ratings from match data
- **`fetch_data.py`** - Downloads and processes raw match data from external sources (football-data.co.uk, BBC)
- **`cache_utils.py`** - Handles JSON caching system (save/load results, cache validation, expiration)
- **`pipeline.py`** - Defines the complete simulation pipeline orchestrating data flow and parameters
- **`simulation.py`** - Contains the Monte Carlo simulation engine (match prediction, points allocation, result tracking)
- **`table.py`** - Manages league table operations (points calculation, standings updates, sorting logic)
- **`load_data.py`** - Loads and preprocesses data from CSV files into usable formats for the simulation engine
- **`remaining_fixtures.py`** - Loads remaining fixtures for the current season (25-26)
