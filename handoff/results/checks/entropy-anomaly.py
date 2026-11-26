import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import Model


def test_equilibrium_zero_excess_entropy():
    """A uniform, force-free equilibrium preparation has zero excess rate."""
    experiment = {
        "force_x": 0.0,
        "force_y": 0.0,
        "drag_ratio": 1.3,
        "magnetic": 2.0,
        "temperature": 1.1,
        "contrast": 0.0,
        "wavenumber": 2,
        "bath_contrast": 0.0,
        "switch_rate": 0.8,
        "detector_phase": 0.7,
    }

    # The calibration fit is unrelated to this exact identity.  Supplying a
    # valid fitted coefficient lets this check exercise only the prediction
    # API and keeps the test runnable against the starter implementation.
    model = Model()
    model.friction = 1.0
    result = model.predict([experiment])[0]

    assert np.isfinite(result)
    assert abs(result) <= 1e-8
