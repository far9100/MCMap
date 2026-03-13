"""
HeightMap image loader.
Converts grayscale pixel values (0-255) to Minecraft Y-coordinates.
"""

import numpy as np
from PIL import Image

from .erosion import hydraulic_erosion, thermal_erosion


def _gaussian_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Apply a separable Gaussian blur using pure numpy (no scipy)."""
    # Build 1-D kernel: radius = 3*sigma, odd size
    radius = max(1, int(3 * sigma))
    size   = 2 * radius + 1
    x      = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    # Separable convolution: pad with edge values to avoid border artefacts
    def conv1d(a: np.ndarray, ax: int) -> np.ndarray:
        pad = [(0, 0)] * a.ndim
        pad[ax] = (radius, radius)
        padded = np.pad(a, pad, mode="edge")
        out = np.zeros_like(a)
        for i, w in enumerate(kernel):
            slices = [slice(None)] * a.ndim
            slices[ax] = slice(i, i + a.shape[ax])
            out += w * padded[tuple(slices)]
        return out
    return conv1d(conv1d(arr, 0), 1)


class HeightMap:
    def __init__(self, image_path: str, min_y: int = 1, max_y: int = 200,
                 smooth: bool = True, smooth_sigma: float = 1.5,
                 hydraulic: bool = False, hydraulic_droplets: int = 20_000,
                 thermal: bool = False, thermal_iterations: int = 50,
                 thermal_talus: float = 0.05):
        img = Image.open(image_path).convert("L")
        self.width  = img.width
        self.height = img.height
        self.min_y  = min_y
        self.max_y  = max_y
        # Store heights as 2D numpy array (H, W) for fast slicing
        raw = np.array(img, dtype=np.float32)            # (H, W) 0-255
        if smooth:
            raw = _gaussian_blur(raw, sigma=smooth_sigma)

        # Normalise to [0, 1] for erosion (both algorithms are tuned to this range)
        normalized = raw / 255.0                         # (H, W) float32

        if thermal or hydraulic:
            # Erosion functions use [x, z] = [col, row] indexing → transpose
            arr = normalized.T.astype(np.float64)        # (W, H)
            if thermal:
                arr = thermal_erosion(arr, iterations=thermal_iterations,
                                      talus_angle=thermal_talus)
            if hydraulic:
                arr = hydraulic_erosion(arr, n_droplets=hydraulic_droplets)
            normalized = arr.T.astype(np.float32)        # back to (H, W)

        self._heights = np.round(
            min_y + (max_y - min_y) * normalized
        ).astype(np.int32)                                # (H, W)

    def get_height(self, px: int, pz: int) -> int:
        """Return the MC Y height for pixel coordinate (px, pz)."""
        if px < 0 or px >= self.width or pz < 0 or pz >= self.height:
            return self.min_y
        return int(self._heights[pz, px])

    def get_region(self, px0: int, pz0: int, pw: int, ph: int) -> np.ndarray:
        """
        Return a (ph, pw) int32 array of heights, clamped to image bounds.
        Out-of-bounds pixels are filled with min_y.
        """
        out = np.full((ph, pw), self.min_y, dtype=np.int32)
        # Compute valid source / destination slices
        src_x0 = max(px0, 0);          dst_x0 = src_x0 - px0
        src_x1 = min(px0 + pw, self.width);  dst_x1 = dst_x0 + (src_x1 - src_x0)
        src_z0 = max(pz0, 0);          dst_z0 = src_z0 - pz0
        src_z1 = min(pz0 + ph, self.height); dst_z1 = dst_z0 + (src_z1 - src_z0)
        if src_x1 > src_x0 and src_z1 > src_z0:
            out[dst_z0:dst_z1, dst_x0:dst_x1] = \
                self._heights[src_z0:src_z1, src_x0:src_x1]
        return out
