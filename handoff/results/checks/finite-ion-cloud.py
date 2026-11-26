import json
from pathlib import Path

import numpy as np

from model import Model


def test_one_ion_boundary_formula_and_disk_radius_independence():
    """The exact N=1 partition integral is a useful physical smoke test."""
    records = json.loads(
        (Path(__file__).parents[1] / "data" / "calibration.json").read_text()
    )
    model = Model().fit(records)
    g = model.coupling
    ratio = 1.5
    u = 0.3
    gamma = u * g

    # Directly evaluate the derived one-ion expression in this test; a is
    # absent because it cancels from the dimensionless observable.
    exponent = 2.0 - gamma
    if abs(exponent) < 1e-10:
        expected = (1.0 - ratio**-2) / (2.0 * np.log(ratio))
    else:
        expected = exponent * (ratio * ratio - 1.0) * ratio**(-gamma) / (
            2.0 * (ratio**exponent - 1.0)
        )

    experiments = [
        {"ion_count": 1, "temperature_multiplier": u,
         "radius_ratio": ratio, "disk_radius": 0.7},
        {"ion_count": 1, "temperature_multiplier": u,
         "radius_ratio": ratio, "disk_radius": 1.6},
    ]
    predicted = model.predict(experiments)
    assert predicted.shape == (2,)
    assert np.all(np.isfinite(predicted))
    assert np.allclose(predicted, expected, rtol=0.0, atol=1e-12)
    assert predicted[0] == predicted[1]
    assert abs(predicted[0] - records[0]["value"]) < 0.003
