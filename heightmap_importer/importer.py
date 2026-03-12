"""
Core import orchestrator for Minecraft Java Edition 1.21.1.

Workflow:
  1. Copy the source world to the output directory.
  2. Read each affected chunk from the OUTPUT region files.
  3. Apply heightmap terrain block-by-block.
  4. Save modified region files back to the output directory.
"""

import shutil
from pathlib import Path

import numpy as np
import nbtlib
from tqdm import tqdm

from .heightmap import HeightMap
from .region import get_or_create_region
from .chunk import apply_heightmap_chunk, update_heightmaps, WORLD_MIN_Y, WORLD_MAX_Y


# DataVersion for Minecraft Java Edition 1.21.1
DATA_VERSION = 3955


def import_heightmap(
    world_dir:  str,
    output_dir: str,
    image_path: str,
    origin_x:   int,
    origin_z:   int,
    min_y:      int  = -60,
    max_y:      int  = 200,
    sea_level:  int  = 63,
    snow_line:  int  = 140,
    scale:      int  = 1,
    verbose:    bool = True,
) -> None:
    """
    Apply a grayscale heightmap to a Minecraft 1.21.1 world.
    """
    # ------------------------------------------------------------------
    # 1. Copy world to output directory
    # ------------------------------------------------------------------
    src = Path(world_dir)
    dst = Path(output_dir)

    if verbose:
        print(f"Copying world to output folder: {dst} ...")

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    if verbose:
        print("Copy complete.")

    # ------------------------------------------------------------------
    # 2. Prepare
    # ------------------------------------------------------------------
    hm      = HeightMap(image_path, min_y=min_y, max_y=max_y)
    total_x = hm.width  * scale
    total_z = hm.height * scale

    chunk_x0 = origin_x >> 4
    chunk_z0 = origin_z >> 4
    chunk_x1 = (origin_x + total_x - 1) >> 4
    chunk_z1 = (origin_z + total_z - 1) >> 4

    total_chunks = (chunk_x1 - chunk_x0 + 1) * (chunk_z1 - chunk_z0 + 1)

    # Cache open RegionFile objects (keyed by region coords)
    open_regions: dict = {}

    def get_region(cx: int, cz: int):
        key = (cx >> 5, cz >> 5)
        if key not in open_regions:
            open_regions[key] = get_or_create_region(str(dst), cx, cz)
        return open_regions[key]

    # ------------------------------------------------------------------
    # 3. Iterate chunks and apply terrain
    # ------------------------------------------------------------------
    chunk_iter = (
        (chunk_x, chunk_z)
        for chunk_z in range(chunk_z0, chunk_z1 + 1)
        for chunk_x in range(chunk_x0, chunk_x1 + 1)
    )

    with tqdm(
        total=total_chunks,
        desc="  Chunks",
        unit="chunk",
        disable=not verbose,
        bar_format="{desc}: {n_fmt}/{total_fmt} [{bar:30}] {percentage:5.1f}%  elapsed {elapsed}  ETA {remaining}",
        dynamic_ncols=True,
    ) as pbar:
        for chunk_x, chunk_z in chunk_iter:
            region   = get_region(chunk_x, chunk_z)
            cx_local = chunk_x & 31
            cz_local = chunk_z & 31

            chunk_nbt = region.read_chunk_nbt(cx_local, cz_local)
            if chunk_nbt is None:
                chunk_nbt = _blank_chunk(chunk_x, chunk_z)

            # Build surface_grid (16×16) as numpy array
            surface_grid = np.full((16, 16), min_y, dtype=np.int32)

            # Compute which pixel columns overlap this chunk
            for local_bx in range(16):
                world_x = chunk_x * 16 + local_bx
                if world_x < origin_x or world_x >= origin_x + total_x:
                    continue
                px = (world_x - origin_x) // scale

                for local_bz in range(16):
                    world_z = chunk_z * 16 + local_bz
                    if world_z < origin_z or world_z >= origin_z + total_z:
                        continue
                    pz = (world_z - origin_z) // scale
                    surface_grid[local_bz, local_bx] = hm.get_height(px, pz)

            # Apply terrain and heightmap in one vectorised pass each
            apply_heightmap_chunk(chunk_nbt, surface_grid, sea_level, snow_line)
            update_heightmaps(chunk_nbt, surface_grid)
            region.write_chunk_nbt(cx_local, cz_local, chunk_nbt)

            pbar.update(1)

    # ------------------------------------------------------------------
    # 4. Flush all modified region files
    # ------------------------------------------------------------------
    if verbose:
        print(f"Saving {len(open_regions)} region file(s)...")
    for rf in open_regions.values():
        rf.save()

    if verbose:
        print(f"Done. Output world: {dst}")


# ---------------------------------------------------------------------------
# Blank chunk factory – 1.21.1 format (no "Level" wrapper)
# ---------------------------------------------------------------------------

def _blank_chunk(chunk_x: int, chunk_z: int) -> nbtlib.File:
    """Create a minimal valid chunk for MC 1.21.1."""
    return nbtlib.File({
        "DataVersion":   nbtlib.Int(DATA_VERSION),
        "xPos":          nbtlib.Int(chunk_x),
        "zPos":          nbtlib.Int(chunk_z),
        "yPos":          nbtlib.Int(-4),          # minimum section Y
        "Status":        nbtlib.String("minecraft:full"),
        "LastUpdate":    nbtlib.Long(0),
        "InhabitedTime": nbtlib.Long(0),
        "isLightOn":     nbtlib.Byte(0),
        "sections":      nbtlib.List[nbtlib.Compound](),
        "Heightmaps":    nbtlib.Compound(),
        "block_entities": nbtlib.List[nbtlib.Compound](),
        "fluid_ticks":   nbtlib.List[nbtlib.Compound](),
        "block_ticks":   nbtlib.List[nbtlib.Compound](),
        "PostProcessing": nbtlib.List[nbtlib.List](),
        "structures": nbtlib.Compound({
            "References": nbtlib.Compound(),
            "starts":     nbtlib.Compound(),
        }),
    })
