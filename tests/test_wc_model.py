import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldcup.data import load_elo
from worldcup.model import EloModel, ScorelineDist, sample_scoreline, seeded_rng


def test_scoreline_dist_wdl_and_sample():
    grid = np.zeros((11, 11))
    grid[1, 0] = 0.5
    grid[1, 1] = 0.25
    grid[0, 1] = 0.25
    dist = ScorelineDist(grid)

    assert dist.wdl == (0.5, 0.25, 0.25)
    assert sample_scoreline(dist, seeded_rng(2026)) in {(1, 0), (1, 1), (0, 1)}


def test_elo_model_matches_wdl_targets():
    model = EloModel(load_elo())
    dist = model.predict("Spain", "Cape Verde")
    p_home, p_draw, p_away = dist.wdl

    assert dist.grid.shape == (11, 11)
    assert np.isclose(dist.grid.sum(), 1)
    assert p_home > 0.7
    assert np.isclose(p_draw, 0.26)
    assert p_away < 0.05
