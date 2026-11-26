import json
from pathlib import Path

import numpy as np
import pytest

from model import Model


def test_zero_interaction_has_zero_response():
    """A constant zero potential cannot exert a solute force on the sphere."""
    records = json.loads(
        (Path(__file__).parents[1] / "data" / "calibration.json").read_text()
    )
    model = Model().fit(records)
    experiment = {
        "radius": 1.0,
        "width": 1.0,
        "strength": 0.0,
        "slip": 0.0,
    }
    prediction = model.predict([experiment])
    assert prediction.shape == (1,)
    assert np.isfinite(prediction[0])
    assert prediction[0] == pytest.approx(0.0, abs=1e-12)


def test_attraction_and_repulsion_have_derivation_signs():
    records = json.loads(
        (Path(__file__).parents[1] / "data" / "calibration.json").read_text()
    )
    model = Model().fit(records)
    experiments = [
        {"radius": 1.0, "width": 1.0, "strength": -1.0, "slip": 0.0},
        {"radius": 1.0, "width": 1.0, "strength": 1.0, "slip": 0.0},
    ]
    attractive, repulsive = model.predict(experiments)
    assert attractive > 0.0
    assert repulsive < 0.0
