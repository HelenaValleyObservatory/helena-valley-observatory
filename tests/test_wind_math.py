import math

import numpy as np
import pytest

from fl_wind import angle_diff, bearing_mean_weighted


def test_angle_diff_normal_case():
    assert angle_diff(0, 90) == 90
    assert angle_diff(90, 0) == -90


def test_angle_diff_wraparound():
    # Going from 350 forward to 10 is +20, not -340.
    assert angle_diff(350, 10) == 20
    assert angle_diff(10, 350) == -20


def test_angle_diff_antipodal_boundary():
    # (b - a + 180) % 360 - 180 can only ever land on -180, never +180,
    # for an exact antipodal pair. Pin this down so a future refactor
    # doesn't silently flip the sign convention here.
    assert angle_diff(0, 180) == -180
    assert angle_diff(180, 0) == -180


def test_bearing_mean_simple_average():
    assert bearing_mean_weighted(np.array([0, 90])) == pytest.approx(45.0)


def test_bearing_mean_wraparound_boundary():
    # A naive arithmetic mean of [350, 10] gives 180 -- exactly backwards.
    # The vector (cos/sin) mean must resolve this to ~0/360 instead.
    assert bearing_mean_weighted(np.array([350, 10])) == pytest.approx(0.0, abs=1e-6)
    assert bearing_mean_weighted(np.array([359, 1])) == pytest.approx(0.0, abs=1e-6)


def test_bearing_mean_weighted_toward_dominant_angle():
    result = bearing_mean_weighted(np.array([0, 90]), weights=np.array([3, 1]))
    expected = math.degrees(math.atan2(1, 3))
    assert result == pytest.approx(expected)
