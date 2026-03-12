"""
Block layer definitions for terrain generation.
Minecraft Java Edition 1.21.1 – world Y range: -64 to 319.
"""

AIR          = "minecraft:air"
BEDROCK      = "minecraft:bedrock"
STONE        = "minecraft:stone"
DIRT         = "minecraft:dirt"
GRASS_BLOCK  = "minecraft:grass_block"
SAND         = "minecraft:sand"
SNOW_BLOCK   = "minecraft:snow_block"

# Absolute bottom of the world in 1.18+
WORLD_MIN_Y = -64


def get_block_for_layer(
    y: int,
    surface_y: int,
    sea_level: int = 63,
    snow_line: int = 140,
) -> str:
    """
    Return the block name for world Y coordinate `y` given the surface height.

    Layering rules:
      y == WORLD_MIN_Y              → bedrock
      y >  surface_y                → air
      depth 0, surface >= snow_line → snow_block
      depth 0 (above sea)           → grass_block
      depth 0 (at/below sea)        → sand
      depth 1-3 (above sea)         → dirt
      depth 1-3 (at/below sea)      → sand
      deeper                        → stone
    """
    if y == WORLD_MIN_Y:
        return BEDROCK
    if y > surface_y:
        return AIR

    depth = surface_y - y  # 0 = surface

    if surface_y <= sea_level:
        if depth <= 3:
            return SAND
        return STONE

    if depth == 0:
        return SNOW_BLOCK if surface_y >= snow_line else GRASS_BLOCK
    if depth <= 3:
        return DIRT
    return STONE
