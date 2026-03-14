"""
Loader for terrain_colors.json.

Both preview.py and biome_editor.py import `load()` to get colour
parameters.  Falls back to built-in defaults when the file is missing
or malformed, so the program never crashes due to a bad JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

# ── Built-in defaults (mirror terrain_colors.json) ────────────────────────
_DEFAULTS: dict = {
    "mode": "stepped",
    "color_bands": [
        {"min_y":  -64, "color": "#336333"},
        {"min_y":  -48, "color": "#3B7236"},
        {"min_y":  -32, "color": "#438139"},
        {"min_y":  -16, "color": "#4B903C"},
        {"min_y":    0, "color": "#569D40"},
        {"min_y":   16, "color": "#61A945"},
        {"min_y":   32, "color": "#6DB54A"},
        {"min_y":   48, "color": "#7AC050"},
        {"min_y":   64, "color": "#8BC556"},
        {"min_y":   80, "color": "#9DCA5C"},
        {"min_y":   96, "color": "#AFCF61"},
        {"min_y":  112, "color": "#C0CE59"},
        {"min_y":  128, "color": "#D1CA48"},
        {"min_y":  144, "color": "#DDC03A"},
        {"min_y":  160, "color": "#E1AA31"},
        {"min_y":  176, "color": "#E59528"},
        {"min_y":  192, "color": "#E17A1F"},
        {"min_y":  208, "color": "#DC6017"},
        {"min_y":  224, "color": "#CF4613"},
        {"min_y":  240, "color": "#BE2D11"},
        {"min_y":  256, "color": "#B01C0F"},
        {"min_y":  272, "color": "#A4160D"},
        {"min_y":  288, "color": "#98100C"},
        {"min_y":  304, "color": "#8C0A0A"},
    ],
    "heatmap": {
        "green":              [0.0, 0.55, 0.0],
        "red":                [1.0, 0.0,  0.0],
        "green_zone_top_y":  -32,
        "red_zone_bot_y":    283,
        "anchor_step_blocks": 16,
    },
    "world_bounds": {
        "min_y": -64,
        "max_y": 319,
    },
}

_JSON_PATH = Path(__file__).parent.parent / "terrain_colors.json"


def load() -> dict:
    """
    Load terrain_colors.json, merging with defaults for any missing keys.

    Returns a dict with the same top-level structure as _DEFAULTS.
    """
    try:
        with open(_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _deep_copy_defaults()

    result: dict = _deep_copy_defaults()
    # Override top-level scalar fields
    if "mode" in data:
        result["mode"] = data["mode"]
    if "color_bands" in data:
        result["color_bands"] = data["color_bands"]
    if "biome_colors" in data:
        result["biome_colors"] = data["biome_colors"]
    if "biome_fallback_color" in data:
        result["biome_fallback_color"] = data["biome_fallback_color"]
    # Shallow-merge dict sections
    for section in ("heatmap", "world_bounds"):
        if section in data and isinstance(data[section], dict):
            result[section] = {**result[section], **data[section]}
    return result


def to_rgb_float(color) -> list[float]:
    """
    Normalise a colour value to [r, g, b] floats in [0, 1].
    Accepts either a '#RRGGBB' hex string or an [r, g, b] float list.
    """
    if isinstance(color, str):
        h = color.lstrip("#")
        return [int(h[0:2], 16) / 255.0,
                int(h[2:4], 16) / 255.0,
                int(h[4:6], 16) / 255.0]
    return [float(v) for v in color]


def _deep_copy_defaults() -> dict:
    return {
        "mode": _DEFAULTS["mode"],
        "color_bands": [dict(b) for b in _DEFAULTS["color_bands"]],
        "heatmap": dict(_DEFAULTS["heatmap"]),
        "world_bounds": dict(_DEFAULTS["world_bounds"]),
        "biome_colors": dict(_DEFAULTS.get("biome_colors", {})),
        "biome_fallback_color": _DEFAULTS.get("biome_fallback_color", "#888888"),
    }
