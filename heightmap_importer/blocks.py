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
GRAVEL       = "minecraft:gravel"
WATER        = "minecraft:water"

# Absolute bottom of the world in 1.18+
WORLD_MIN_Y = -64


def get_block_for_layer(
    y: int,
    surface_y: int,
    snow_line:   int = 192,
    rock_line:   int = 128,
    gravel_line: int = 72,
    water_level: int = 64,
    soil_depth:  int = 3,
) -> str:
    """
    Return the block name for world Y coordinate `y` given the surface height.

    Height zones (surface_y-based):
      surface_y >= snow_line                     → snow_block surface
      rock_line   <= surface_y < snow_line       → stone surface (bare rock)
      gravel_line <= surface_y < rock_line       → gravel surface (2 layers)
      surface_y <  gravel_line                   → grass_block surface

    Water fill:
      y > surface_y AND y < water_level          → water
    """
    if y == WORLD_MIN_Y:
        return BEDROCK
    if y > surface_y:
        return WATER if y < water_level else AIR

    depth = surface_y - y  # 0 = surface

    if surface_y >= snow_line:
        if depth == 0:
            return SNOW_BLOCK
        if depth < soil_depth:
            return DIRT
        return STONE

    if surface_y >= rock_line:
        return STONE

    if surface_y >= gravel_line:
        if depth < 2:
            return GRAVEL
        return STONE

    # Grass zone
    if depth == 0:
        return GRASS_BLOCK
    if depth < soil_depth:
        return DIRT
    return STONE
