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
# Fixed block palette (indices 0-6)
# ---------------------------------------------------------------------------

_PALETTE_NAMES = [
    "minecraft:air",         # 0
    "minecraft:bedrock",     # 1
    "minecraft:stone",       # 2
    "minecraft:dirt",        # 3
    "minecraft:grass_block", # 4
    "minecraft:sand",        # 5
    "minecraft:snow_block",  # 6
]
_N_PALETTE  = len(_PALETTE_NAMES)
_BPB        = max(4, math.ceil(math.log2(_N_PALETTE)))   # 3 bits → use 4
_BPL        = 64 // _BPB                                  # 16 blocks per long
_N_LONGS    = math.ceil(4096 / _BPL)                     # 256 longs


def _make_palette_nbt() -> nbtlib.List:
    return nbtlib.List[nbtlib.Compound]([
        nbtlib.Compound({"Name": nbtlib.String(name)})
        for name in _PALETTE_NAMES
    ])


# ---------------------------------------------------------------------------
# Vectorised block computation (numpy)
# ---------------------------------------------------------------------------

def _compute_section_indices(
    sec_y:        int,
    surface_grid: np.ndarray,   # (16, 16) z×x, int32  (world Y of surface)
    sea_level:    int,
    snow_line:    int,
) -> np.ndarray:
    """
    Return a (16,16,16) uint8 array of palette indices for one section.
    Layout: [y_local, z, x].
    """
    base = sec_y * 16                                          # world Y at local_y==0
    ly   = np.arange(16, dtype=np.int32)
    # Broadcast to full (16,16,16) so boolean masks match `out` exactly
    wy   = np.broadcast_to(
               (base + ly)[:, np.newaxis, np.newaxis], (16, 16, 16)
           ).copy()                                             # (16,16,16)
    sy   = np.broadcast_to(
               surface_grid[np.newaxis, :, :], (16, 16, 16)
           ).copy()                                             # (16,16,16)

    out  = np.zeros((16, 16, 16), dtype=np.uint8)             # 0 = air

    valid   = (wy >= WORLD_MIN_Y) & (wy <= WORLD_MAX_Y)       # (16,16,16)
    solid   = valid & (wy <= sy)
    bedrock = valid & (wy == WORLD_MIN_Y)
    depth   = sy - wy                                          # (16,16,16)
    on_land = sy > sea_level                                   # (16,16,16)

    # Bedrock row
    out[bedrock] = 1

    above_bed = solid & ~bedrock

    # Stone: depth ≥ 4
    out[above_bed & (depth >= 4)] = 2

    # Underwater (surface at/below sea level): sand for top 4 layers
    out[above_bed & (depth < 4) & ~on_land] = 5

    # Land: depth 1-3 → dirt
    out[above_bed & (depth >= 1) & (depth <= 3) & on_land] = 3

    # Surface on land
    surf = above_bed & (depth == 0) & on_land
    out[surf & (sy >= snow_line)] = 6   # snow_block
    out[surf & (sy < snow_line)]  = 4   # grass_block

    return out


# ---------------------------------------------------------------------------
# Vectorised bit packing (numpy)  – avoids Python-level loops entirely
# ---------------------------------------------------------------------------

def _pack_indices_numpy(flat: np.ndarray, bpb: int) -> np.ndarray:
    """
    Pack a 1-D uint64 array of palette indices into signed int64 longs.

    flat : 1-D ndarray, length == 4096
    bpb  : bits per block
    Returns int64 ndarray of length ceil(4096 / (64 // bpb)).
    """
    bpl     = 64 // bpb
    n_longs = math.ceil(len(flat) / bpl)
    pad     = n_longs * bpl - len(flat)
    if pad:
        flat = np.concatenate([flat, np.zeros(pad, dtype=np.uint64)])
    arr    = flat.reshape(n_longs, bpl)
    shifts = (np.arange(bpl, dtype=np.uint64) * bpb)
    packed = np.bitwise_or.reduce(arr << shifts, axis=1)  # uint64
    return packed.view(np.int64)                           # reinterpret as signed


# ---------------------------------------------------------------------------
# Public chunk-level API
# ---------------------------------------------------------------------------

def apply_heightmap_chunk(
    chunk_nbt:    nbtlib.Compound,
    surface_grid: np.ndarray,   # (16, 16) z×x, int32
    sea_level:    int,
    snow_line:    int,
) -> None:
    """
    Replace block_states in every section of a chunk based on surface_grid.

    This overwrites existing block data in each column that the heightmap
    covers.  Sections that are entirely air are omitted (or removed if they
    exist and become empty) — MC ignores missing sections.
    """
    sections: nbtlib.List = chunk_nbt.get("sections", nbtlib.List[nbtlib.Compound]())
    if "sections" not in chunk_nbt:
        chunk_nbt["sections"] = sections

    # Build lookup: sec_y → index in sections list
    sec_map = {int(s["Y"]): i for i, s in enumerate(sections)}

    surf_max = int(surface_grid.max())

    for sec_y in range(MIN_SECTION_Y, MAX_SECTION_Y + 1):
        sec_base = sec_y * 16

        # Skip sections entirely above the tallest surface (except bedrock)
        if sec_y != MIN_SECTION_Y and sec_base > surf_max:
            continue

        indices = _compute_section_indices(sec_y, surface_grid, sea_level, snow_line)
        flat    = indices.flatten().astype(np.uint64)

        # Check if section is all-air → skip / remove
        if flat.max() == 0:
            if sec_y in sec_map:
                # Remove the air-only section to keep file lean
                del sections[sec_map[sec_y]]
                # Rebuild map after deletion
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
            # Single block type → single-entry palette, no data array
            block_name = _PALETTE_NAMES[int(unique[0])]
            bs["palette"] = nbtlib.List[nbtlib.Compound]([
                nbtlib.Compound({"Name": nbtlib.String(block_name)})
            ])
            bs.pop("data", None)
        else:
            bs["palette"] = _make_palette_nbt()
            packed = _pack_indices_numpy(flat, _BPB)
            # nbtlib.LongArray is a np.ndarray subclass — pass directly
            bs["data"] = nbtlib.LongArray(packed)


def update_heightmaps(
    chunk_nbt:    nbtlib.Compound,
    surface_grid: np.ndarray,   # (16, 16) z×x, int32
) -> None:
    """
    Write WORLD_SURFACE / MOTION_BLOCKING heightmaps.
    Stored value = surface_y + 64 + 1  (9-bit, 7-per-long, no-span packing).
    """
    hm = chunk_nbt.get("Heightmaps", nbtlib.Compound())
    chunk_nbt["Heightmaps"] = hm

    bpb     = 9
    bpl     = 7          # 64 // 9
    n_longs = 37         # ceil(256 / 7)

    vals = (surface_grid.flatten().astype(np.int64) + 65).astype(np.uint64)
    pad  = n_longs * bpl - 256
    arr  = np.concatenate([vals, np.zeros(pad, dtype=np.uint64)]).reshape(n_longs, bpl)
    shifts = np.arange(bpl, dtype=np.uint64) * bpb
    packed = np.bitwise_or.reduce(arr << shifts, axis=1).view(np.int64)

    longs = nbtlib.LongArray(packed)
    hm["WORLD_SURFACE"]   = longs
    hm["MOTION_BLOCKING"] = longs
