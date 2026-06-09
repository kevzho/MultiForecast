import json
import os
from datetime import datetime
import hashlib
import logging

CACHE_DIR = "cache"

def ensure_cache_dir():
    """Create cache directory if it doesn't exist"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_key(data_source, params=None):
    """
    Generate a unique cache key based on input
    """
    base = f"simulations_{data_source}"
    if params:
        #add parameters to cache key if they matter
        param_str = json.dumps(params, sort_keys=True)
        base += hashlib.md5(param_str.encode()).hexdigest()[:8]
    return base

def save_to_cache(cache_key, data, metadata=None):
    """
    Save data to cache with metadata
    """
    ensure_cache_dir()
    
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    #define cache entry structure
    cache_entry = {
        "data": data,
        "metadata": metadata or {},
        "cached_at": datetime.now().isoformat()
    }
    
    with open(cache_file, "w") as f:
        json.dump(cache_entry, f, indent=2)
    
    logging.info(f"Cached to {cache_file}")

def load_from_cache(cache_key, max_age_hours=24):
    """
    Load from cache if exists and not too old
    Returns None if cache miss or expired
    """
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    
    if not os.path.exists(cache_file):
        logging.info(f"Cache miss: {cache_key}")
        return None
    
    with open(cache_file, "r") as f:
        cache_entry = json.load(f)
    
    #check age if max_age_hours specified
    if max_age_hours > 0:
        cached_time = datetime.fromisoformat(cache_entry["cached_at"])
        age = datetime.now() - cached_time
        if age.total_seconds() > max_age_hours * 3600:
            logging.info(f"Cache expired: {cache_key} (age: {age})")
            return None
    
    logging.info(f"Cache hit: {cache_key}")
    return cache_entry["data"]

def save_simulation_results(results, cache_key="latest_simulations"):
    """
    Specifically save your simulation results
    """
    metadata = {
        "num_teams": len(results['teams']),
        "num_simulations": results['metadata']['num_simulations'],
        "timestamp": results['metadata']['timestamp']
    }
    save_to_cache(cache_key, results, metadata)

def load_simulation_results(cache_key="latest_simulations", max_age_hours=24):
    """
    Load your simulation results
    """
    return load_from_cache(cache_key, max_age_hours)

def clear_cache():
    """Delete all cache files"""
    if os.path.exists(CACHE_DIR):
        for file in os.listdir(CACHE_DIR):
            if file.endswith('.json'):
                os.remove(os.path.join(CACHE_DIR, file))
        logging.info("🧹 Cache cleared")