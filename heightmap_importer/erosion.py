"""
Erosion algorithms adapted from far9100/MCPyLib_terrain.

Both functions operate on normalized float64 arrays (values in [0.0, 1.0])
with shape (W, D) indexed [x, z] (column-first, i.e. transposed from the
typical image convention of [row, col] = [z, x]).

Callers are responsible for normalizing / denormalizing and transposing
the heightmap array before and after calling these functions.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Internal helpers for hydraulic erosion
# ---------------------------------------------------------------------------

def _compute_gradient(
    h: np.ndarray, px: float, pz: float
) -> tuple[float, float]:
    """Bilinear-interpolated gradient at float position (px, pz)."""
    w, d = h.shape
    ix = min(int(px), w - 2)
    iz = min(int(pz), d - 2)
    fx = px - ix
    fz = pz - iz
    gx = (h[ix + 1, iz] - h[ix, iz]) * (1 - fz) + (h[ix + 1, iz + 1] - h[ix, iz + 1]) * fz
    gz = (h[ix, iz + 1] - h[ix, iz]) * (1 - fx) + (h[ix + 1, iz + 1] - h[ix + 1, iz]) * fx
    return gx, gz


def _interpolate_height(h: np.ndarray, px: float, pz: float) -> float:
    """Bilinear interpolation of height at float position (px, pz)."""
    w, d = h.shape
    ix = min(int(px), w - 2)
    iz = min(int(pz), d - 2)
    fx = px - ix
    fz = pz - iz
    return (
        h[ix,     iz    ] * (1 - fx) * (1 - fz)
        + h[ix + 1, iz    ] * fx       * (1 - fz)
        + h[ix,     iz + 1] * (1 - fx) * fz
        + h[ix + 1, iz + 1] * fx       * fz
    )


def _apply_erosion_radius(
    h: np.ndarray,
    px: float, pz: float,
    amount: float,
    radius: int,
) -> None:
    """Erode cells within `radius` of (px, pz), weighted by linear falloff."""
    w, d = h.shape
    ix, iz = int(px), int(pz)
    weight_sum = 0.0
    cells: list[tuple[int, int, float]] = []
    for dx in range(-radius, radius + 1):
        for dz in range(-radius, radius + 1):
            nx, nz = ix + dx, iz + dz
            if 0 <= nx < w and 0 <= nz < d:
                dist = (dx * dx + dz * dz) ** 0.5
                w_val = max(0.0, radius - dist)
                cells.append((nx, nz, w_val))
                weight_sum += w_val
    if weight_sum > 0:
        for nx, nz, w_val in cells:
            h[nx, nz] -= amount * w_val / weight_sum


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def hydraulic_erosion(
    heightmap: np.ndarray,
    n_droplets: int        = 20_000,
    seed: int              = 42,
    inertia: float         = 0.05,
    capacity_factor: float = 4.0,
    deposition_rate: float = 0.3,
    erosion_rate: float    = 0.3,
    evaporation: float     = 0.01,
    gravity: float         = 4.0,
    min_slope: float       = 0.01,
    max_steps: int         = 120,
    radius: int            = 3,
) -> np.ndarray:
    """
    Simulate hydraulic (water-droplet) erosion on a 2-D heightmap.

    Parameters
    ----------
    heightmap : np.ndarray
        Shape (W, D), float64, values in [0, 1].  Indexed [x, z].
    n_droplets : int
        Number of water droplets to simulate.  Larger = more erosion detail,
        longer runtime (each droplet runs a Python loop).
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    np.ndarray  Same shape and dtype as input, eroded heightmap.
    """
    h = heightmap.astype(np.float64)
    w, d = h.shape
    rng = np.random.default_rng(seed)

    for _ in range(n_droplets):
        px = rng.random() * (w - 1)
        pz = rng.random() * (d - 1)
        dir_x, dir_z = 0.0, 0.0
        water    = 1.0
        sediment = 0.0
        speed    = 1.0

        for _step in range(max_steps):
            gx, gz = _compute_gradient(h, px, pz)
            dir_x = dir_x * inertia - gx * (1 - inertia)
            dir_z = dir_z * inertia - gz * (1 - inertia)

            length = (dir_x * dir_x + dir_z * dir_z) ** 0.5
            if length < 1e-9:
                break
            dir_x /= length
            dir_z /= length

            new_px = px + dir_x
            new_pz = pz + dir_z
            if not (0 <= new_px < w - 1 and 0 <= new_pz < d - 1):
                break

            height_diff = (
                _interpolate_height(h, new_px, new_pz)
                - _interpolate_height(h, px, pz)
            )
            capacity = max(-height_diff, min_slope) * speed * water * capacity_factor

            if sediment > capacity or height_diff > 0:
                deposit = (
                    min(sediment, height_diff)
                    if height_diff > 0
                    else (sediment - capacity) * deposition_rate
                )
                ix = min(int(px), w - 1)
                iz = min(int(pz), d - 1)
                h[ix, iz] += deposit
                sediment  -= deposit
            else:
                erode = min((capacity - sediment) * erosion_rate, -height_diff)
                _apply_erosion_radius(h, px, pz, erode, radius)
                sediment += erode

            speed  = max(speed * speed + height_diff * gravity, 1e-8) ** 0.5
            water *= (1 - evaporation)
            px, pz = new_px, new_pz

    return h.astype(heightmap.dtype)


def thermal_erosion(
    heightmap: np.ndarray,
    iterations: int    = 50,
    talus_angle: float = 0.05,
) -> np.ndarray:
    """
    Simulate thermal erosion (scree / talus collapse) on a 2-D heightmap.

    Parameters
    ----------
    heightmap : np.ndarray
        Shape (W, D), float64, values in [0, 1].  Indexed [x, z].
    iterations : int
        Number of passes.  More passes = smoother slopes.
    talus_angle : float
        Height-difference threshold in normalised [0, 1] units that
        triggers mass transfer.  Default 0.05 means slopes steeper than
        5 % of the full height range will collapse.

    Returns
    -------
    np.ndarray  Same shape and dtype as input, eroded heightmap.
    """
    h = heightmap.astype(np.float64)

    for _ in range(iterations):
        diff_xp = np.zeros_like(h)
        diff_xm = np.zeros_like(h)
        diff_zp = np.zeros_like(h)
        diff_zm = np.zeros_like(h)

        diff_xp[:-1, :] = h[:-1, :] - h[1:,  :]
        diff_xm[1:,  :] = h[1:,  :] - h[:-1, :]
        diff_zp[:, :-1] = h[:, :-1]  - h[:, 1:]
        diff_zm[:, 1:]  = h[:, 1:]   - h[:, :-1]

        for diff, axis, direction in [
            (diff_xp, 0,  1),
            (diff_xm, 0, -1),
            (diff_zp, 1,  1),
            (diff_zm, 1, -1),
        ]:
            excess   = np.maximum(diff - talus_angle, 0.0)
            transfer = excess * 0.5 * 0.25
            h -= transfer
            h += np.roll(transfer, direction, axis=axis)

    return h.astype(heightmap.dtype)
