# -*- coding: utf-8; -*-
"""
Star FWHM measurement for ranking frames by seeing, in arcseconds.

Added in the CMOS fork of PlanetarySystemStacker. The original ranking methods
("xy gradient", "Laplace", "Sobel") measure overall sharpness, which suits the
Moon, Sun and planets. For star fields the natural quality measure is the
full width at half maximum (FWHM) of the stars: the smaller, the better the
seeing in that frame. This module measures it in two ways:

- "median": find the brightest unsaturated stars in the frame, fit each with a
  2-D Gaussian and return the median FWHM (robust: no input needed);
- "reference": measure only the star nearest to a given position (within a
  search radius, so it is found again when the image wobbles).

FWHM values are in pixels; multiply by the pixel scale (arcsec/pixel) to get
arcseconds.

Copyright (C) the CMOS fork contributors. This file is part of the fork of
PlanetarySystemStacker and, like it, is distributed under the GNU General
Public License version 3 or later (see License/).
"""

from math import inf, sqrt, log

import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.optimize import least_squares

SIGMA_TO_FWHM = 2.0 * sqrt(2.0 * log(2.0))  # 2.3548
MIN_FWHM = 1.5  # pixels; anything narrower is a hot pixel or cosmic ray, not a star


def saturation_level(frame, bg=None, noise=None):
    """The level at which this frame saturates, or None if no star seems saturated.

    Saturated stars have flat tops: many pixels sit at (almost) the frame's maximum.
    Their FWHM is meaningless, so stars reaching 95% of this level are skipped.
    """
    hi = float(frame.max())
    if bg is not None and hi < bg + 100 * noise:  # nothing bright enough to saturate
        return None
    if np.count_nonzero(frame >= hi - max(1.0, 0.002 * hi)) >= 5:
        return 0.95 * hi
    return None


def background_and_noise(frame):
    """Robust background level and noise (median, 1.4826 * MAD) from a pixel sample."""
    sample = frame[::max(1, frame.shape[0] // 256), ::max(1, frame.shape[1] // 256)].ravel()
    bg = float(np.median(sample))
    noise = 1.4826 * float(np.median(np.abs(sample - bg)))
    if noise < 0.5:  # very flat integer data (short exposures): MAD rounds to 0
        near = sample[np.abs(sample - bg) <= 10]
        noise = float(np.std(near)) if near.size else 0.0
    return bg, max(noise, 0.5)


def fit_star(frame, x, y, bg, half=7):
    """Fit a circular 2-D Gaussian plus constant to the cutout around (x, y).

    :return: (FWHM in pixels, fitted centre x, fitted centre y) or None if the fit failed.
    """
    ny, nx = frame.shape
    x0, x1, y0, y1 = int(x) - half, int(x) + half + 1, int(y) - half, int(y) + half + 1
    if x0 < 0 or y0 < 0 or x1 > nx or y1 > ny:
        return None
    cut = frame[y0:y1, x0:x1].astype(np.float64)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    amp0 = float(cut.max() - bg)
    if amp0 <= 0:
        return None

    def model(p):
        a, cx, cy, s, b = p
        return a * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s * s)) + b

    try:
        r = least_squares(lambda p: (model(p) - cut).ravel(), [amp0, x, y, 2.0, bg],
                          bounds=([0, x0, y0, 0.3, -np.inf], [np.inf, x1, y1, half, np.inf]),
                          max_nfev=200)
    except (ValueError, np.linalg.LinAlgError):
        return None
    if not r.success:
        return None
    a, cx, cy, s, b = r.x
    # Reject fits that ran into the bounds or wandered off the star.
    if s >= half * 0.95 or abs(cx - x) > 3 or abs(cy - y) > 3 or SIGMA_TO_FWHM * s < MIN_FWHM:
        return None
    return SIGMA_TO_FWHM * s, cx, cy


def find_stars(frame, bg, noise, max_stars=25, threshold=10.0, saturation=None, edge=8):
    """Positions (x, y) of the brightest isolated, unsaturated stars, brightest first."""
    smooth = gaussian_filter(frame.astype(np.float32), 1.5)
    peaks = (smooth == maximum_filter(smooth, size=9)) & (smooth > bg + threshold * noise)
    peaks[:edge, :] = peaks[-edge:, :] = peaks[:, :edge] = peaks[:, -edge:] = False
    ys, xs = np.nonzero(peaks)
    if saturation is not None:  # skip stars with any saturated pixel near the peak
        local_max = maximum_filter(frame, size=5)
        keep = local_max[ys, xs] < saturation
        ys, xs = ys[keep], xs[keep]
    order = np.argsort(smooth[ys, xs])[::-1][:max_stars * 2]
    return [(float(xs[i]), float(ys[i])) for i in order]


def frame_fwhm(frame, mode="median", reference=None, search_radius=25, max_stars=25,
               saturation="auto"):
    """FWHM in pixels of one frame (smaller is better), or inf if no star could be measured.

    :param frame: 2-D image (any numeric dtype)
    :param mode: "median" (many stars) or "reference" (the star nearest to `reference`)
    :param reference: (x, y) of the reference star in frame pixels (0-based), for mode "reference"
    :param search_radius: how far (pixels) the reference star may have moved
    :param max_stars: how many stars to fit in mode "median"
    :param saturation: pixel value at and above which stars are skipped ("auto": detect)
    :return: (FWHM in pixels, number of stars used, list of (x, y, fwhm) per star)
    """
    frame = np.asarray(frame)
    if frame.ndim == 3:  # colour: use the mean of the planes
        frame = frame.mean(axis=2)
    bg, noise = background_and_noise(frame)
    if isinstance(saturation, str):
        saturation = saturation_level(frame, bg, noise)

    if mode == "reference" and reference is not None:
        rx, ry = reference
        ny, nx = frame.shape
        x0, x1 = max(0, int(rx - search_radius)), min(nx, int(rx + search_radius) + 1)
        y0, y1 = max(0, int(ry - search_radius)), min(ny, int(ry + search_radius) + 1)
        if x1 <= x0 or y1 <= y0:
            return inf, 0, []
        win = gaussian_filter(frame[y0:y1, x0:x1].astype(np.float32), 1.5)
        iy, ix = np.unravel_index(int(np.argmax(win)), win.shape)
        if win[iy, ix] < bg + 5 * noise:
            return inf, 0, []
        res = fit_star(frame, x0 + ix, y0 + iy, bg)
        if res is None:
            return inf, 0, []
        return res[0], 1, [(res[1], res[2], res[0])]

    stars = []
    for x, y in find_stars(frame, bg, noise, max_stars=max_stars, saturation=saturation):
        res = fit_star(frame, x, y, bg)
        if res is not None:
            stars.append((res[1], res[2], res[0]))
        if len(stars) >= max_stars:
            break
    if not stars:
        return inf, 0, []
    return float(np.median([s[2] for s in stars])), len(stars), stars
