# -*- coding: utf-8; -*-
"""
Per-job settings for the CMOS fork of PlanetarySystemStacker.

A job input "<name>.ser" (or any other input) may come with "<name>.pss.json",
written by CMOS Browser when it prepares frames for lucky imaging:

    {
      "rank_method": "FWHM (arcsec)",      # or "Laplace", "xy gradient", "Sobel"
      "pixel_scale": 0.2272,               # arcsec per pixel
      "fwhm_mode": "median" | "reference",
      "reference_star": [x, y] | null,     # frame pixels, 0-based
      "search_radius": 25,                 # pixels
      "source": {...}                      # free-form description (shown in the log)
    }

Jobs without such a file run with the program's normal settings.

This file is part of the CMOS fork of PlanetarySystemStacker and is distributed
under the GNU General Public License version 3 or later (see License/).
"""

import json
from csv import writer
from os.path import exists, splitext

SETTINGS = {  # json key -> configuration attribute
    "rank_method": "rank_frames_method",
    "pixel_scale": "rank_frames_pixel_scale",
    "fwhm_mode": "rank_frames_fwhm_mode",
    "reference_star": "rank_frames_reference_star",
    "search_radius": "rank_frames_search_radius",
}


def settings_file(job_name):
    return splitext(job_name)[0] + ".pss.json"


def apply_job_settings(configuration, job_name):
    """Apply the job's .pss.json settings (or restore the defaults). Returns the dict or None."""
    if not hasattr(configuration, "_cmos_defaults"):
        configuration._cmos_defaults = {a: getattr(configuration, a) for a in SETTINGS.values()}
    for attr, value in configuration._cmos_defaults.items():
        setattr(configuration, attr, value)
    path = settings_file(job_name)
    if not exists(path):
        return None
    with open(path) as f:
        settings = json.load(f)
    for key, attr in SETTINGS.items():
        if key in settings:
            value = settings[key]
            if key == "reference_star" and value is not None:
                value = (float(value[0]), float(value[1]))
            setattr(configuration, attr, value)
    return settings


def describe_fwhm(rank_frames, csv_name=None):
    """Summary lines of the per-frame FWHM (arcsec), and optionally a CSV with one row per frame."""
    fw = rank_frames.frame_fwhm_arcsec_original
    if not fw:
        return []
    good = sorted(v for v in fw if v != float("inf"))
    if csv_name:
        with open(csv_name, "w", newline="") as f:
            w = writer(f)
            w.writerow(["frame", "fwhm_arcsec", "stars_measured", "rank"])
            for i, v in enumerate(fw):
                w.writerow([i + 1, "" if v == float("inf") else round(v, 3),
                            rank_frames.frame_fwhm_stars_original[i],
                            rank_frames.rank_indices_original[i] + 1])
    if not good:
        return ["           Star FWHM: no star measured in any frame"]
    pct = lambda p: good[min(len(good) - 1, int(p * len(good)))]
    lines = ["           Star FWHM (arcsec): best %.2f, 10%% %.2f, median %.2f, worst %.2f"
             % (good[0], pct(0.1), pct(0.5), good[-1]),
             "           Frames without a measurable star: %d of %d" % (len(fw) - len(good), len(fw))]
    if csv_name:
        lines.append("           Per-frame FWHM written to " + csv_name)
    return lines
