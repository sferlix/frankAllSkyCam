'''
Unit tests for the night moon model in starscalc.py (analyze_sky_robust with
moon_brightness and a night_calibration on a fully dark sky):

1. moon_sky_brightness follows the lunar phase law.
2. The radiance rate is scored against the calibrated clear-sky rate for the Moon.
3. The sky colour separates blue moonlit clear sky from grey or yellow cloud.
4. The moon-aware star floor expects fewer stars under moonlight.
5. Declustering is skipped under a calibrated dark sky only.
6. Without a calibration or moon_brightness, or with the Sun above -18 degrees, the
   previous signals apply; features are reported for nightcalib.

Synthetic arrays; they check the behaviour and the gating.
'''

import cv2
import numpy as np
import pytest

from frankAllSkyCam import starscalc as sc

HEIGHT, WIDTH = 768, 1024
DARK = dict(sun_alt_deg=-30.0)
CAL = dict(clear_rate=0.65, moon_rate_coeff=15.0, nbr_clear_dark=0.12, nbr_clear_slope=0.46,
           clear_star_count=95.0)


def _sky(bgr):
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    img[:, :] = bgr
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sky = sc.roi_mask(gray, 0.65)
    return img, gray, sky


def _bgr_for(nbr, gray_level):
    # a colour with the given NBR = (B-R)/(B+R) whose gray value is about gray_level
    b, r = 40 * (1 + nbr), 40 * (1 - nbr)
    g = (gray_level - 0.114 * b - 0.299 * r) / 0.587
    return (round(b), round(g), round(r))


def _expected_clear_nbr(moon_brightness):
    clear_rate = sc._clear_sky_rate(moon_brightness, CAL)
    frac = CAL['moon_rate_coeff'] * moon_brightness / clear_rate
    return CAL['nbr_clear_dark'] + CAL['nbr_clear_slope'] * frac


# --- 1. phase law ---------------------------------------------------------------

def test_moon_sky_brightness():
    assert sc.moon_sky_brightness(None, 0.5) is None
    assert sc.moon_sky_brightness(30.0, None) is None
    assert sc.moon_sky_brightness(-5.0, 1.0) == 0.0
    assert sc.moon_sky_brightness(90.0, 1.0) == pytest.approx(1.0)
    # a half Moon is roughly a tenth of a full one, far less than the illuminated fraction
    assert 0.05 < sc.moon_sky_brightness(90.0, 0.5) < 0.12
    assert sc.moon_sky_brightness(30.0, 0.9) < sc.moon_sky_brightness(60.0, 0.9)


# --- 2./3. rate and colour ---------------------------------------------------------

def _cloud(bgr_img, gray, sky, exposure, mb):
    return sc._estimate_cloud_cover_moon_model(bgr_img, gray, sky, sky, exposure, mb, CAL)


@pytest.mark.parametrize("moon_brightness", [0.0, 0.1, 0.5])
def test_clear_sky_at_the_expected_rate_and_colour_reads_clear(moon_brightness):
    img, gray, sky = _sky(_bgr_for(_expected_clear_nbr(moon_brightness) + 0.05, 30))
    exposure = gray[sky == 255].mean() / sc._clear_sky_rate(moon_brightness, CAL)
    assert _cloud(img, gray, sky, exposure, moon_brightness) < 5.0


def test_bright_moonlit_overcast_reads_cloudy():
    mb = 0.2
    img, gray, sky = _sky(_bgr_for(0.26, 36))
    exposure = gray[sky == 255].mean() / (4.0 * sc._clear_sky_rate(mb, CAL))
    assert _cloud(img, gray, sky, exposure, mb) > 90.0


def test_grey_moonlit_sky_reads_cloudy_from_colour_alone():
    # rate exactly at the clear-sky value, but grey instead of blue
    mb = 0.3
    img, gray, sky = _sky(_bgr_for(0.25, 30))
    exposure = gray[sky == 255].mean() / sc._clear_sky_rate(mb, CAL)
    assert _cloud(img, gray, sky, exposure, mb) > 90.0


def test_yellow_light_polluted_overcast_reads_cloudy_without_moon():
    img, gray, sky = _sky(_bgr_for(-0.4, 40))
    exposure = gray[sky == 255].mean() / (1.7 * CAL['clear_rate'])
    assert _cloud(img, gray, sky, exposure, 0.0) == 100.0


# --- 4. star floor ------------------------------------------------------------------

def test_moon_aware_star_floor():
    f = sc._star_deficit_floor_moon_model
    assert f(None, 0.0, CAL) == 0.0
    assert f(0, 0.0, CAL) == 100.0
    assert f(60, 0.0, CAL) == 0.0
    # a dim Moon still expects enough stars for an empty sky to mean cloud
    assert f(1, 0.03, CAL) == 100.0
    # a bright Moon expects so few stars that a count means nothing
    assert f(0, 0.5, CAL) == 0.0


# --- 5. declustering ------------------------------------------------------------------

def _star_cluster_frame():
    gray = np.full((HEIGHT, WIDTH), 25, dtype=np.uint8)
    for i in range(4):
        for j in range(4):
            cv2.circle(gray, (480 + 7 * i, 360 + 7 * j), 1, 200, -1)
    return gray


def test_star_counts_with_and_without_declustering():
    gray = _star_cluster_frame()
    sky = sc.roi_mask(gray, 0.65)
    assert sc._star_counts(gray, sky, 30, 0.4) == (0, 16)
    assert sc._find_stars(gray, sky, 30, 0.4) == 0


@pytest.fixture
def no_static_mask(monkeypatch):
    monkeypatch.setattr(sc, "_get_obstruction_mask",
                        lambda gray, roi, is_night, mask_path=None: np.zeros_like(gray))


def test_calibrated_dark_sky_keeps_the_clump(tmp_path, no_static_mask):
    path = str(tmp_path / "clump.png")
    cv2.imwrite(path, cv2.cvtColor(_star_cluster_frame(), cv2.COLOR_GRAY2BGR))

    def stars(**kw):
        return sc.analyze_sky_robust(path, 0.65, 0.4, 30, exposure_secs=30.0, **DARK, **kw)[0]

    assert stars(moon_brightness=0.0, night_calibration=CAL) == 16
    assert stars(moon_brightness=0.2, night_calibration=CAL) == 0
    assert stars(moon_brightness=0.0) == 0          # not calibrated yet
    assert stars() == 0


# --- 6. gating and features -----------------------------------------------------------

def _grey_frame(tmp_path):
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    img[:, :] = _bgr_for(0.25, 30)
    path = str(tmp_path / "grey.png")
    cv2.imwrite(path, img)
    return path


def test_moon_model_needs_calibration_moon_brightness_and_a_dark_sky(tmp_path, no_static_mask):
    path = _grey_frame(tmp_path)
    exposure = 30.0 / sc._clear_sky_rate(0.3, CAL)
    args = dict(exposure_secs=exposure, skip_star_detection=True, moon_factor=0.5)

    def cloud(**kw):
        return sc.analyze_sky_robust(path, 0.65, 0.4, 30, **args, **kw)[1]

    with_model = cloud(moon_brightness=0.3, night_calibration=CAL, **DARK)
    previous = cloud(**DARK)
    assert with_model > 90.0                                    # grey under a bright Moon: cloud
    assert previous < 30.0                                      # rate less moonlight, no colour
    assert cloud(moon_brightness=0.3, **DARK) == previous       # no calibration yet
    assert cloud(night_calibration=CAL, **DARK) == previous     # Moon unknown
    assert cloud(moon_brightness=0.3, night_calibration=CAL, sun_alt_deg=-15.0) == \
        cloud(sun_alt_deg=-15.0)                                # twilight


def test_features_are_reported_before_calibration(tmp_path, no_static_mask):
    path = _grey_frame(tmp_path)
    feats = {}
    sc.analyze_sky_robust(path, 0.65, 0.4, 30, exposure_secs=10.0, moon_brightness=0.2, features=feats, **DARK)
    assert feats['rate'] == pytest.approx(3.0, abs=0.1)
    assert feats['nbr'] == pytest.approx(0.25, abs=0.02)
    assert feats['stars'] == 0 and feats['moon_brightness'] == 0.2 and feats['sun_alt'] == -30.0
    assert feats['moon_in_frame'] is False

    none = {}
    sc.analyze_sky_robust(path, 0.65, 0.4, 30, moon_brightness=0.2, features=none, **DARK)  # no exposure
    assert none == {}
