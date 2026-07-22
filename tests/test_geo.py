import pytest

from fl_segment import haversine_nm


def test_haversine_same_point_is_zero():
    assert haversine_nm(46.6031, -112.0146, 46.6031, -112.0146) == pytest.approx(0.0, abs=1e-9)


def test_haversine_one_degree_latitude_is_about_60nm():
    # 1 nautical mile was historically defined as 1 arcminute of latitude,
    # so 1 degree of latitude should land close to 60 nm regardless of longitude.
    assert haversine_nm(0, 0, 1, 0) == pytest.approx(60.04, abs=0.1)


def test_haversine_is_symmetric():
    a = (46.6031, -112.0146)
    b = (47.0, -111.0)
    assert haversine_nm(*a, *b) == pytest.approx(haversine_nm(*b, *a))
