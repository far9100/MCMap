"""
Minecraft Chunk NBT editor — numpy-accelerated.
Targets Java Edition 1.21.1 (DataVersion 3955) – Anvil format.

Optimisation strategy
---------------------
Instead of the old per-column set_block_column (256 calls/chunk, each
unpack+repack 4096 longs), we compute the entire 4096-block section array
with a single vectorised numpy operation, then pack it in one pass.

BlockStates packing (unchanged since 1.16):
  bits_per_block   = max(4, ceil(log2(palette_size)))
  blocks_per_long  = 64 // bits_per_block   (NO spanning across longs)
  indices packed LSB-first within each long
"""

import math

import numpy as np
import nbtlib

# ---------------------------------------------------------------------------
# World / section constants
# ---------------------------------------------------------------------------

WORLD_MIN_Y   = -64
WORLD_MAX_Y   = 319
MIN_SECTION_Y = -4    # section covering Y -64..-49
MAX_SECTION_Y = 19    # section covering Y 304..319
NUM_SECTIONS  = MAX_SECTION_Y - MIN_SECTION_Y + 1  # 24

# ---------------------------------------------------------------------------
# Fixed palette indices (always present at the same position)
# ---------------------------------------------------------------------------

_IDX_AIR     = 0
_IDX_BEDROCK = 1
_IDX_STONE   = 2
_IDX_DIRT    = 3
_IDX_WATER   = 4

_BASE_BLOCKS = [
    "minecraft:air",      # 0
    "minecraft:bedrock",  # 1
    "minecraft:stone",    # 2
    "minecraft:dirt",     # 3
    "minecraft:water",    # 4
]


# ---------------------------------------------------------------------------
# Palette builder
# ---------------------------------------------------------------------------

def build_palette(surface_layers: list[dict]) -> tuple[list[str], dict[str, int]]:
    """
    Build the block palette for this world type.

    Base blocks (air, bedrock, stone, dirt, water) always occupy indices 0-4.
    Surface blocks from config are appended in order of first appearance and
    their palette indices are written back into each layer dict as 'palette_idx'.

    Returns (palette_names, name_to_idx).
    """
    names: list[str]      = list(_BASE_BLOCKS)
    name_to_idx: dict[str, int] = {n: i for i, n in enumerate(names)}

    for layer in surface_layers:
        name = layer["block"]
        if name not in name_to_idx:
            name_to_idx[name] = len(names)
            names.append(name)
        layer["palette_idx"] = name_to_idx[name]

        if "steep_block" in layer:
            sname = layer["steep_block"]
            if sname not in name_to_idx:
                name_to_idx[sname] = len(names)
                names.append(sname)
            layer["steep_palette_idx"] = name_to_idx[sname]

    return names, name_to_idx


# ---------------------------------------------------------------------------
# Per-section helpers
# ---------------------------------------------------------------------------


def _compute_surface_depth(
    surface_grid: np.ndarray,   # (16, 16) int32
    chunk_cx:     int,
    chunk_cz:     int,
    min_depth:    int,
    max_depth:    int,
) -> np.ndarray:
    """
    Compute per-column surface block depth in [min_depth, max_depth].

    Depth is shaped by two factors:
      • Slope  — flat terrain → max_depth; steep slopes (≥3) → min_depth.
      • Noise  — spatially coherent variation (seed 999) adds organic irregularity
                 without chunk-boundary discontinuities.

    Returns (16, 16) int32.
    """
    min_depth = max(1, min_depth)
    if max_depth <= min_depth:
        return np.full((16, 16), min_depth, dtype=np.int32)

    grad_z, grad_x = np.gradient(surface_grid.astype(np.float32))
    slope = np.sqrt(grad_x ** 2 + grad_z ** 2)

    # slope 0 → slope_factor = 1 (平地→深);  slope ≥ 3 → slope_factor = 0 (陡坡→淺)
    slope_factor = np.clip(1.0 - slope / 3.0, 0.0, 1.0).astype(np.float32)

    # Coherent noise in [0, 1) — seed differs from blend noise to be independent
    noise = _smooth_blend_noise(chunk_cx, chunk_cz, global_seed=999)

    # 將 slope_factor 與 noise 合併為 t ∈ [0, 1]
    # noise 在 ±0.25 內微調 t，使變化有機但不超出範圍
    t = np.clip(slope_factor + (noise - 0.5) * 0.5, 0.0, 1.0).astype(np.float32)
    return np.round(min_depth + t * (max_depth - min_depth)).astype(np.int32)


def _smooth_blend_noise(chunk_cx: int, chunk_cz: int, global_seed: int = 0) -> np.ndarray:
    """
    Return a (16, 16) float32 array indexed [z_local, x_local] with values in
    [0, 1).  Uses value noise on a coarse 8-block grid with smoothstep bilinear
    interpolation so the noise field is spatially continuous across chunk
    boundaries, eliminating the salt-and-pepper seams caused by independent
    per-chunk random seeds.
    """
    SPACING = 8   # coarse-grid cell size in blocks
    GS      = 4   # sample points per axis (covers 24 blocks, safely > 16)

    wx0 = chunk_cx * 16
    wz0 = chunk_cz * 16
    gi0 = wx0 // SPACING   # base coarse X index
    gz0 = wz0 // SPACING   # base coarse Z index

    # Hash each coarse-grid point (gi0+xi, gz0+zi) → float in [0, 1)
    coarse = np.empty((GS, GS), dtype=np.float32)
    for xi in range(GS):
        for zi in range(GS):
            h = int(gi0 + xi) * 374761393 ^ int(gz0 + zi) * 668265263 ^ int(global_seed)
            h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFF_FFFF
            h ^= h >> 16
            coarse[xi, zi] = (h & 0x7FFF_FFFF) / 0x7FFF_FFFF

    # Fractional positions in the coarse grid for each local column/row
    xs = wx0 + np.arange(16, dtype=np.float32)   # world X, shape (16,)
    zs = wz0 + np.arange(16, dtype=np.float32)   # world Z, shape (16,)
    fx = xs / SPACING - gi0                        # (16,) in [0, GS)
    fz = zs / SPACING - gz0                        # (16,)

    ix = np.clip(fx.astype(np.int32), 0, GS - 2)
    iz = np.clip(fz.astype(np.int32), 0, GS - 2)
    tx = np.clip(fx - ix.astype(np.float32), 0.0, 1.0).astype(np.float32)
    tz = np.clip(fz - iz.astype(np.float32), 0.0, 1.0).astype(np.float32)

    # Smoothstep for C¹-continuous interpolation
    tx = tx * tx * (3.0 - 2.0 * tx)
    tz = tz * tz * (3.0 - 2.0 * tz)

    # ix/tx vary along local X → axis 1; iz/tz vary along local Z → axis 0
    ix2d = ix[np.newaxis, :]           # (1, 16)
    iz2d = iz[:, np.newaxis]           # (16, 1)
    tx2d = tx[np.newaxis, :]           # (1, 16)
    tz2d = tz[:, np.newaxis]           # (16, 1)

    c00 = coarse[ix2d,     iz2d    ]   # (16, 16)
    c10 = coarse[ix2d + 1, iz2d    ]
    c01 = coarse[ix2d,     iz2d + 1]
    c11 = coarse[ix2d + 1, iz2d + 1]

    return (c00 * (1.0 - tx2d) * (1.0 - tz2d) +
            c10 *        tx2d  * (1.0 - tz2d) +
            c01 * (1.0 - tx2d) *        tz2d  +
            c11 *        tx2d  *        tz2d)   # (16, 16) float32


def _select_surface_blocks(
    surface_grid:   np.ndarray,   # (16, 16) int32
    surface_layers: list[dict],   # each has: block, max_y, min_y, blend, palette_idx
    chunk_cx:       int,
    chunk_cz:       int,
) -> np.ndarray:
    """
    For each column select the surface block palette index based on height zones
    and linear blending at BOTH zone boundaries.

    Processing order: ascending max_y (lowest zone first, highest zone last).
    Higher-priority layers (higher max_y) run last and overwrite lower ones,
    so their blend zones take effect correctly.

    Each layer blends at two edges:
      • Lower blend  [min_y - blend, min_y):  probability rises  0 → 1
      • Full zone    [min_y, max_y]:           probability = 1
      • Upper blend  (max_y, max_y + blend]:  probability falls  1 → 0

    Optional per-layer steep override:
      • slope_threshold: float — columns whose gradient magnitude exceeds this
        value will use steep_block instead of block.
      • steep_block: str — block name to use on steep slopes (must also be
        defined in config so it ends up in the palette).

    col_rand is derived from spatially coherent value noise keyed on world
    coordinates, so adjacent chunks produce a continuous noise field and
    transition boundaries have no visible chunk-aligned seams.

    Returns (16, 16) uint8 of palette indices.
    """
    col_rand = _smooth_blend_noise(chunk_cx, chunk_cz)   # (16, 16) in [0, 1)

    result = np.full((16, 16), _IDX_STONE, dtype=np.uint8)   # fallback: stone

    # Pre-compute slope once for steep-block substitution
    grad_z, grad_x = np.gradient(surface_grid.astype(np.float32))
    slope = np.sqrt(grad_x ** 2 + grad_z ** 2)

    # Ascending max_y: low zones run first, high zones overwrite last
    for layer in surface_layers:
        pidx  = int(layer["palette_idx"])
        max_y = int(layer["max_y"])
        min_y = int(layer["min_y"])
        blend = int(layer["blend"])
        sy    = surface_grid                                   # (16,16) int32

        slope_threshold = layer.get("slope_threshold")
        # steep_block is optional; falls back to stone when absent
        steep_pidx = layer.get("steep_palette_idx", _IDX_STONE) if slope_threshold is not None else None

        assigned = np.zeros((16, 16), dtype=bool)

        # Full zone – always assign
        mask = (sy >= min_y) & (sy <= max_y)
        result[mask] = pidx
        assigned |= mask

        if blend > 0:
            # Lower blend: [min_y-blend, min_y)  probability rises 0 → 1
            lo_floor = min_y - blend
            lo_zone  = (sy >= lo_floor) & (sy < min_y)
            lo_prob  = (sy.astype(np.float32) - lo_floor) / blend
            lo_mask  = lo_zone & (col_rand < lo_prob)
            result[lo_mask] = pidx
            assigned |= lo_mask

            # Upper blend: (max_y, max_y+blend]  probability falls 1 → 0
            hi_ceil = max_y + blend
            hi_zone = (sy > max_y) & (sy <= hi_ceil)
            hi_prob = (hi_ceil - sy.astype(np.float32)) / blend
            hi_mask = hi_zone & (col_rand < hi_prob)
            result[hi_mask] = pidx
            assigned |= hi_mask

        # Steep override: replace with steep_block where slope exceeds threshold
        if slope_threshold is not None:
            result[assigned & (slope > slope_threshold)] = steep_pidx

    return result


def _compute_section_indices(
    sec_y:                int,
    surface_grid:         np.ndarray,   # (16,16) z×x int32
    surface_block_grid:   np.ndarray,   # (16,16) z×x uint8 (palette idx)
    water_level:          int,
    palette_names:        list[str],
    surface_depth_grid:   np.ndarray,   # (16,16) z×x int32  (1..max_depth)
    floor_y:              int = WORLD_MIN_Y,
    top_surface_block_grid: np.ndarray | None = None,   # (16,16) overrides depth-0 block
) -> np.ndarray:
    """
    Return a (16,16,16) uint8 array of palette indices for one section.
    Layout: [y_local, z, x].

    floor_y: the lowest Y that receives a bedrock block; everything below is air.
    This is driven by config min_y so the user's height floor is respected.

    Subsurface rules:
      Surface block layer: surface_depth blocks of the surface block, then stone.
    """
    base = sec_y * 16
    ly   = np.arange(16, dtype=np.int32)

    wy = np.broadcast_to(
        (base + ly)[:, np.newaxis, np.newaxis], (16, 16, 16)
    ).copy()                                                    # (16,16,16)
    sy = np.broadcast_to(
        surface_grid[np.newaxis, :, :], (16, 16, 16)
    ).copy()
    sb = np.broadcast_to(
        surface_block_grid[np.newaxis, :, :], (16, 16, 16)
    ).copy()
    tsb_source = top_surface_block_grid if top_surface_block_grid is not None else surface_block_grid
    tsb = np.broadcast_to(
        tsb_source[np.newaxis, :, :], (16, 16, 16)
    ).copy()
    sdd = np.broadcast_to(
        surface_depth_grid[np.newaxis, :, :], (16, 16, 16)
    ).copy()

    out   = np.zeros((16, 16, 16), dtype=np.uint8)             # 0 = air
    valid = (wy >= floor_y) & (wy <= WORLD_MAX_Y)
    depth = sy - wy                                             # 0=surface, +ve=below

    # Water fill: above surface AND below water_level
    out[valid & (wy > sy) & (wy < water_level)] = _IDX_WATER

    solid     = valid & (wy <= sy)
    bedrock   = valid & (wy == floor_y)
    above_bed = solid & ~bedrock

    out[bedrock] = _IDX_BEDROCK

    # Top block (depth 0): may use a different block (e.g. grass_block over dirt)
    out[above_bed & (depth == 0)] = tsb[above_bed & (depth == 0)]

    # Subsurface block layer: depth 1 … sdd-1
    sub_mask = above_bed & (depth > 0) & (depth < sdd)
    out[sub_mask] = sb[sub_mask]

    # Below the surface block layer: stone
    out[above_bed & (depth >= sdd)] = _IDX_STONE

    return out


# ---------------------------------------------------------------------------
# Vectorised bit packing (numpy)
# ---------------------------------------------------------------------------

def _pack_indices_numpy(flat: np.ndarray, bpb: int) -> np.ndarray:
    """
    Pack a 1-D uint64 array of palette indices into signed int64 longs.
    """
    bpl     = 64 // bpb
    n_longs = math.ceil(len(flat) / bpl)
    pad     = n_longs * bpl - len(flat)
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint64)])
    arr    = flat.reshape(n_longs, bpl)
    shifts = np.arange(bpl, dtype=np.uint64) * bpb
    packed = np.bitwise_or.reduce(arr << shifts, axis=1)
    return packed.view(np.int64)


# ---------------------------------------------------------------------------
# Public chunk-level API
# ---------------------------------------------------------------------------

def apply_heightmap_chunk(
    chunk_nbt:      nbtlib.Compound,
    surface_grid:   np.ndarray,     # (16,16) z×x int32
    surface_layers: list[dict],     # from config, with palette_idx already set
    water_level:    int,
    palette_names:  list[str],
    chunk_cx:             int = 0,
    chunk_cz:             int = 0,
    surface_depth_min:    int = 1,
    surface_depth_max:    int = 1,
    floor_y:              int = WORLD_MIN_Y,
    dirt_top_replacement: bool = True,
    dirt_top_block:       str  = "minecraft:grass_block",
) -> None:
    """
    Replace block_states in every section of a chunk based on surface_grid.

    Sections that are entirely air are removed to keep file size lean.
    """
    sections: nbtlib.List = chunk_nbt.get("sections", nbtlib.List[nbtlib.Compound]())
    if "sections" not in chunk_nbt:
        chunk_nbt["sections"] = sections

    sec_map = {int(s["Y"]): i for i, s in enumerate(sections)}

    surf_max = int(surface_grid.max())
    fill_max = max(surf_max, water_level - 1)    # water can raise effective ceiling

    surface_block_grid = _select_surface_blocks(surface_grid, surface_layers, chunk_cx, chunk_cz)

    # Build the top-layer block grid (depth=0 only).
    # When dirt_top_replacement is enabled, columns whose surface block is dirt
    # get dirt_top_block placed at the very top instead.
    top_surface_block_grid = surface_block_grid.copy()
    if dirt_top_replacement and np.any(surface_block_grid == _IDX_DIRT):
        if dirt_top_block not in palette_names:
            palette_names.append(dirt_top_block)
        top_idx = palette_names.index(dirt_top_block)
        top_surface_block_grid[surface_block_grid == _IDX_DIRT] = top_idx

    surface_depth_grid = _compute_surface_depth(surface_grid, chunk_cx, chunk_cz, surface_depth_min, surface_depth_max)

    n_palette = len(palette_names)
    bpb       = max(4, math.ceil(math.log2(max(n_palette, 2))))
    palette_nbt = nbtlib.List[nbtlib.Compound]([
        nbtlib.Compound({"Name": nbtlib.String(name)})
        for name in palette_names
    ])

    for sec_y in range(MIN_SECTION_Y, MAX_SECTION_Y + 1):
        sec_base = sec_y * 16
        sec_top  = sec_base + 15
        if sec_top < floor_y:        # entire section below floor → all air
            continue
        if sec_base > fill_max:      # entire section above terrain → all air
            continue

        indices = _compute_section_indices(
            sec_y, surface_grid, surface_block_grid,
            water_level, palette_names,
            surface_depth_grid, floor_y,
            top_surface_block_grid,
        )
        flat = indices.flatten().astype(np.uint64)

        # All-air section → skip / remove
        if flat.max() == 0:
            if sec_y in sec_map:
                del sections[sec_map[sec_y]]
                sec_map = {int(s["Y"]): i for i, s in enumerate(sections)}
            continue

        # Get or create section compound
        if sec_y in sec_map:
            sec = sections[sec_map[sec_y]]
        else:
            sec = nbtlib.Compound({
                "Y": nbtlib.Byte(sec_y),
                "block_states": nbtlib.Compound({
                    "palette": nbtlib.List[nbtlib.Compound]([
                        nbtlib.Compound({"Name": nbtlib.String("minecraft:air")})
                    ])
                }),
                "biomes": nbtlib.Compound({
                    "palette": nbtlib.List[nbtlib.String]([
                        nbtlib.String("minecraft:plains")
                    ])
                }),
            })
            sections.append(sec)
            sec_map = {int(s["Y"]): i for i, s in enumerate(sections)}

        bs = sec["block_states"]

        unique = np.unique(flat)
        if len(unique) == 1:
            # Single block type → single-entry palette, no data array needed
            bs["palette"] = nbtlib.List[nbtlib.Compound]([
                nbtlib.Compound({"Name": nbtlib.String(palette_names[int(unique[0])])})
            ])
            bs.pop("data", None)
        else:
            bs["palette"] = palette_nbt
            bs["data"]    = nbtlib.LongArray(_pack_indices_numpy(flat, bpb))


def update_heightmaps(
    chunk_nbt:    nbtlib.Compound,
    surface_grid: np.ndarray,   # (16,16) z×x int32
) -> None:
    """
    Write WORLD_SURFACE / MOTION_BLOCKING heightmaps.
    Stored value = surface_y + 64 + 1  (9-bit, 7-per-long, no-span packing).
    """
    hm = chunk_nbt.get("Heightmaps", nbtlib.Compound())
    chunk_nbt["Heightmaps"] = hm

    bpb     = 9
    bpl     = 7
    n_longs = 37

    vals   = (surface_grid.flatten().astype(np.int64) + 65).astype(np.uint64)
    pad    = n_longs * bpl - 256
    arr    = np.concatenate([vals, np.zeros(pad, dtype=np.uint64)]).reshape(n_longs, bpl)
    shifts = np.arange(bpl, dtype=np.uint64) * bpb
    packed = np.bitwise_or.reduce(arr << shifts, axis=1).view(np.int64)

    longs = nbtlib.LongArray(packed)
    hm["WORLD_SURFACE"]   = longs
    hm["MOTION_BLOCKING"] = longs
