"""
HeightMap image loader.
Converts grayscale pixel values (0-255) to Minecraft Y-coordinates.
"""

import numpy as np
from PIL import Image


class HeightMap:
    def __init__(self, image_path: str, min_y: int = 1, max_y: int = 200):
        img = Image.open(image_path).convert("L")
        self.width  = img.width
        self.height = img.height
        self.min_y  = min_y
        self.max_y  = max_y
        # Store heights as 2D numpy array (H, W) for fast slicing
        raw = np.array(img, dtype=np.float32)            # (H, W) 0-255
        self._heights = np.round(
            min_y + (max_y - min_y) * raw / 255.0
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
