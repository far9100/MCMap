"""
Minecraft Anvil region file (.mca) reader / writer.
Compatible with Java Edition 1.21.1.

Format reference: https://minecraft.wiki/w/Region_file_format

Header (8192 bytes):
  [0   – 4095]  chunk locations  – 1024 × 4 bytes
  [4096 – 8191] chunk timestamps – 1024 × 4 bytes

Location entry (4 bytes):
  bytes 0-2 (big-endian) : sector offset from file start (unit = 4096-byte sector)
  byte  3                : sector count occupied by this chunk's data blob

Chunk data blob (starting at offset * 4096):
  4 bytes (big-endian) : byte-length of (compression_type + compressed_data)
  1 byte               : compression scheme  1 = gzip  2 = zlib
  N bytes              : compressed NBT
"""

import io
import struct
import zlib
import gzip
from pathlib import Path
from typing import Optional, Tuple, Dict

import nbtlib


SECTOR_SIZE      = 4096
HEADER_SECTORS   = 2
COMPRESSION_GZIP = 1
COMPRESSION_ZLIB = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _region_path(world_dir: str, chunk_x: int, chunk_z: int) -> Path:
    rx = chunk_x >> 5
    rz = chunk_z >> 5
    return Path(world_dir) / "region" / f"r.{rx}.{rz}.mca"


def _loc_index(cx_local: int, cz_local: int) -> int:
    return (cx_local & 31) + (cz_local & 31) * 32


# ---------------------------------------------------------------------------
# RegionFile
# ---------------------------------------------------------------------------

class RegionFile:
    """
    In-memory representation of a single .mca region file.

    After making changes via write_chunk_nbt(), call save() to persist.
    """

    def __init__(self, path: Path):
        self.path = path
        # (cx_local, cz_local) → (compression_type: int, compressed_data: bytes)
        self._raw: Dict[Tuple[int, int], Tuple[int, bytes]] = {}
        self._timestamps: Dict[Tuple[int, int], int] = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self):
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        if len(data) < SECTOR_SIZE * HEADER_SECTORS:
            return

        for i in range(1024):
            cx_local = i % 32
            cz_local = i // 32

            # Location entry
            loc_bytes      = b"\x00" + data[i * 4: i * 4 + 3]
            offset_sectors = struct.unpack(">I", loc_bytes)[0]
            sector_count   = data[i * 4 + 3]

            # Timestamp
            ts_off = SECTOR_SIZE + i * 4
            self._timestamps[(cx_local, cz_local)] = struct.unpack_from(">I", data, ts_off)[0]

            if offset_sectors < HEADER_SECTORS or sector_count == 0:
                continue

            byte_offset = offset_sectors * SECTOR_SIZE
            if byte_offset + 5 > len(data):
                continue

            length      = struct.unpack_from(">I", data, byte_offset)[0]
            compression = data[byte_offset + 4]
            compressed  = data[byte_offset + 5: byte_offset + 4 + length]
            self._raw[(cx_local, cz_local)] = (compression, compressed)

    # ------------------------------------------------------------------
    def read_chunk_nbt(self, cx_local: int, cz_local: int) -> Optional[nbtlib.Compound]:
        entry = self._raw.get((cx_local, cz_local))
        if entry is None:
            return None
        compression, compressed = entry
        if compression == COMPRESSION_ZLIB:
            raw = zlib.decompress(compressed)
        elif compression == COMPRESSION_GZIP:
            raw = gzip.decompress(compressed)
        else:
            raise ValueError(f"Unknown chunk compression type: {compression}")
        return nbtlib.File.from_fileobj(io.BytesIO(raw))

    def write_chunk_nbt(self, cx_local: int, cz_local: int, nbt: nbtlib.Compound):
        buf = io.BytesIO()
        # nbtlib.File has a write() method; plain Compound does not.
        if hasattr(nbt, "write"):
            nbt.write(buf)
        else:
            nbtlib.File(nbt).write(buf)
        compressed = zlib.compress(buf.getvalue())
        self._raw[(cx_local, cz_local)] = (COMPRESSION_ZLIB, compressed)

    # ------------------------------------------------------------------
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Build padded payloads for each present chunk
        payloads: Dict[Tuple[int, int], bytes] = {}
        for (cx, cz), (ctype, compressed) in self._raw.items():
            blob    = struct.pack(">I", len(compressed) + 1) + bytes([ctype]) + compressed
            padding = (-len(blob)) % SECTOR_SIZE
            payloads[(cx, cz)] = blob + b"\x00" * padding

        locations  = bytearray(SECTOR_SIZE)
        timestamps = bytearray(SECTOR_SIZE)
        body       = b""
        current_sector = HEADER_SECTORS

        for (cx, cz) in sorted(payloads):
            payload      = payloads[(cx, cz)]
            sector_count = len(payload) // SECTOR_SIZE
            idx          = _loc_index(cx, cz)

            # Write 3-byte big-endian offset + 1-byte count
            locations[idx * 4: idx * 4 + 3] = struct.pack(">I", current_sector)[1:]
            locations[idx * 4 + 3]          = min(sector_count, 255)

            ts = self._timestamps.get((cx, cz), 0)
            struct.pack_into(">I", timestamps, idx * 4, ts)

            body           += payload
            current_sector += sector_count

        self.path.write_bytes(bytes(locations) + bytes(timestamps) + body)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def get_or_create_region(world_dir: str, chunk_x: int, chunk_z: int) -> RegionFile:
    return RegionFile(_region_path(world_dir, chunk_x, chunk_z))
