"""
Biome grid assignment for MCMap.

Maps world coordinates to Minecraft biome IDs using a 2-D grid of cells.
Each cell can have a different biome; the grid is clamped at the edges so
out-of-bounds coordinates always get the nearest valid biome.

Minecraft 1.21.1 stores biomes at 4×4×4 block resolution per section.
"""

import math


class BiomeGrid:
    def __init__(
        self,
        cell_size:      int,
        grid:           list[list[str]] | None,
        origin_x:       int,
        origin_z:       int,
        total_x:        int,
        total_z:        int,
        blend_enabled:  bool = False,
        blend_radius:   int  = 8,
    ):
        self.cell_size     = max(1, cell_size)
        self.origin_x      = origin_x
        self.origin_z      = origin_z
        self.blend_enabled = blend_enabled
        self.blend_radius  = blend_radius

        # Compute required grid dimensions from terrain size
        self.cols = math.ceil(total_x / self.cell_size)
        self.rows = math.ceil(total_z / self.cell_size)

        if grid:
            self._grid = grid
        else:
            # Default: all plains
            self._grid = [["minecraft:plains"] * self.cols for _ in range(self.rows)]

    def _get_cell(self, gz: int, gx: int) -> str:
        """Return the biome for grid cell (gz, gx), clamping to valid range."""
        gz = max(0, min(gz, len(self._grid) - 1))
        row = self._grid[gz]
        gx = max(0, min(gx, len(row) - 1))
        return row[gx]

    def get_biome_at(self, world_x: int, world_z: int) -> str:
        """Return the biome ID for the given world coordinates."""
        rel_x = world_x - self.origin_x
        rel_z = world_z - self.origin_z

        gx = int(rel_x // self.cell_size)
        gz = int(rel_z // self.cell_size)

        if not self.blend_enabled or self.blend_radius <= 0:
            return self._get_cell(gz, gx)

        # Blend at cell boundaries using a noise-free deterministic approach:
        # compute fractional position within the current cell and if within
        # blend_radius of an edge, probabilistically pick the neighbour.
        # We use a simple deterministic hash for the decision.
        cell_local_x = rel_x - gx * self.cell_size
        cell_local_z = rel_z - gz * self.cell_size

        # Distance to each edge
        dist_right  = self.cell_size - cell_local_x
        dist_bottom = self.cell_size - cell_local_z

        # Determine dominant neighbour influence
        in_blend_x = cell_local_x < self.blend_radius or dist_right < self.blend_radius
        in_blend_z = cell_local_z < self.blend_radius or dist_bottom < self.blend_radius

        if not in_blend_x and not in_blend_z:
            return self._get_cell(gz, gx)

        # Simple deterministic hash for blend decision
        h = (int(world_x) * 374761393 ^ int(world_z) * 668265263)
        h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFF_FFFF
        h ^= h >> 16
        t = (h & 0x7FFF_FFFF) / 0x7FFF_FFFF  # [0, 1)

        # Pick neighbour based on which edge is closest
        if in_blend_x and (not in_blend_z or cell_local_x < cell_local_z):
            if cell_local_x < self.blend_radius:
                prob = 1.0 - cell_local_x / self.blend_radius
                if t < prob:
                    return self._get_cell(gz, gx - 1)
            else:
                prob = 1.0 - dist_right / self.blend_radius
                if t < prob:
                    return self._get_cell(gz, gx + 1)
        else:
            if cell_local_z < self.blend_radius:
                prob = 1.0 - cell_local_z / self.blend_radius
                if t < prob:
                    return self._get_cell(gz - 1, gx)
            else:
                prob = 1.0 - dist_bottom / self.blend_radius
                if t < prob:
                    return self._get_cell(gz + 1, gx)

        return self._get_cell(gz, gx)

    def get_section_biomes(self, chunk_cx: int, chunk_cz: int) -> list[str]:
        """
        Return 64 biome strings (XZY order) for one section.

        Each of the 64 entries corresponds to a 4×4×4 block cell within the
        16×16×16 section.  Index = bx + bz*4 + by*16.
        Since this is a 2-D height-based grid, Y is ignored (same biome for
        all Y levels in the same column cell).
        """
        biomes = []
        for _by in range(4):       # Y (ignored for 2-D grid)
            for bz in range(4):    # Z
                for bx in range(4):  # X (innermost)
                    wx = chunk_cx * 16 + bx * 4 + 2  # centre of 4-block cell
                    wz = chunk_cz * 16 + bz * 4 + 2
                    biomes.append(self.get_biome_at(wx, wz))
        return biomes  # length 64
