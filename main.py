#!/usr/bin/env python3
"""
MCMap – HeightMap to Minecraft World Importer
=============================================
Targets: Minecraft Java Edition 1.21.1

預設工作流程：
  1. 讀取 HeightMap 圖片
  2. 渲染 3D 預覽圖（output/preview.png）並開啟
  3. 詢問確認後，才套用至 MC 存檔
  4. 將修改後的存檔輸出至 output/

預設資料夾：
  input/
    heightmaps/   ← 放灰階 PNG HeightMap
    world/        ← 放 MC 存檔（需含 region/ 子資料夾）
  output/         ← 修改後存檔輸出至此

用法範例：
  python main.py --x 0 --z 0
  python main.py --x -512 --z -512 --scale 4 --no-preview
  python main.py --x 0 --z 0 --preview-only
"""

import argparse
import json
import sys
import time
from pathlib import Path

_WORLD_MIN_Y = -64
_WORLD_MAX_Y = 319

DEFAULT_WORLD   = "input/saves"
DEFAULT_HM_DIR  = "input/heightmaps"
DEFAULT_OUTPUT  = "output"
CONFIG_PATH     = Path("config.json")

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config.json if present; return empty dict otherwise."""
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}

_CFG = _load_config()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    _ro = _CFG.get("region_origin", [0, 0])
    _rs = _CFG.get("region_size",   [2, 2])
    _default_x = _ro[0] * 512
    _default_z = _ro[1] * 512

    p = argparse.ArgumentParser(
        description="HeightMap → Minecraft 1.21.1 World Importer（含地形預覽）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--world", "-w", default=DEFAULT_WORLD,
                   help=f"輸入 MC 存檔資料夾（預設：{DEFAULT_WORLD}）")
    p.add_argument("--heightmap", "-i", default=None,
                   help=f"HeightMap 圖片路徑；省略時自動選用 {DEFAULT_HM_DIR}/ 中第一個 .png")
    p.add_argument("--output", "-o", default=DEFAULT_OUTPUT,
                   help=f"輸出資料夾（預設：{DEFAULT_OUTPUT}）")
    p.add_argument("--x", type=int, default=None,
                   help=f"圖片左上角對應的 MC X 座標（省略時由 region_origin 推算，預設：{_default_x}）")
    p.add_argument("--z", type=int, default=None,
                   help=f"圖片左上角對應的 MC Z 座標（省略時由 region_origin 推算，預設：{_default_z}）")
    p.add_argument("--region-origin", nargs=2, type=int, metavar=("RX", "RZ"),
                   default=None,
                   help=f"面朝北時左上角的 region 座標（預設：{_ro[0]} {_ro[1]}）")
    p.add_argument("--region-size", nargs=2, type=int, metavar=("W", "H"),
                   default=None,
                   help=f"地形範圍（單位：region，預設：{_rs[0]} {_rs[1]}，即 {_rs[0]*512}×{_rs[1]*512} 格）")
    p.add_argument("--min-y", type=int, default=_CFG.get("min_y", -60),
                   help=f"像素值 0（黑）對應的 Y 高度（config 預設：{_CFG.get('min_y', -60)}）")
    p.add_argument("--max-y", type=int, default=_CFG.get("max_y", 200),
                   help=f"像素值 255（白）對應的 Y 高度（config 預設：{_CFG.get('max_y', 200)}）")
    p.add_argument("--sea-level", type=int, default=_CFG.get("sea_level", 63),
                   help=f"海平面 Y（預覽用，config 預設：{_CFG.get('sea_level', 63)}）")
    p.add_argument("--snow-line", type=int, default=_CFG.get("snow_line", 192),
                   help=f"雪線 Y（預覽用，config 預設：{_CFG.get('snow_line', 192)}）")
    p.add_argument("--water-level", type=int, default=_CFG.get("water_level", 64),
                   help=f"水面 Y，低於此高度的空氣格填充水（config 預設：{_CFG.get('water_level', 64)}）")
    p.add_argument("--scale", type=int, default=None,
                   help="每像素對應幾個 MC 方塊（整數 ≥ 1；省略時依 region_size 與圖片尺寸自動計算）")

    # Preview flags
    preview_group = p.add_mutually_exclusive_group()
    preview_group.add_argument("--preview-only", action="store_true",
                               help="只渲染預覽圖，不套用至存檔")
    preview_group.add_argument("--no-preview", action="store_true",
                               help="跳過預覽，直接套用至存檔")

    p.add_argument("--no-open", action="store_true",
                   help="渲染預覽後不自動開啟圖片")
    p.add_argument("--yes", "-y", action="store_true",
                   help="預覽後自動確認，不詢問（搭配預覽使用）")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="不顯示進度訊息")
    p.add_argument("--no-terrain-smoothing", action="store_true",
                   default=not _CFG.get("terrain_smoothing", True),
                   help="停用地形平滑（高斯模糊）優化")
    p.add_argument("--smooth-sigma", type=float,
                   default=_CFG.get("smooth_sigma", 2.0),
                   help=f"高斯模糊 sigma（config 預設：{_CFG.get('smooth_sigma', 2.0)}）")
    p.add_argument("--smooth-passes", type=int,
                   default=_CFG.get("smooth_passes", 3),
                   help=f"高斯模糊套用次數（config 預設：{_CFG.get('smooth_passes', 3)}）")

    # Erosion options
    p.add_argument("--no-hydraulic-erosion", action="store_true",
                   default=not _CFG.get("hydraulic_erosion", True),
                   help="停用水力侵蝕模擬（config 預設：開啟）")
    p.add_argument("--hydraulic-droplets", type=int,
                   default=_CFG.get("hydraulic_erosion_droplets", 20_000),
                   help=f"水力侵蝕雨滴數量（config 預設：{_CFG.get('hydraulic_erosion_droplets', 20_000)}）")
    p.add_argument("--no-thermal-erosion", action="store_true",
                   default=not _CFG.get("thermal_erosion", True),
                   help="停用熱侵蝕模擬（config 預設：開啟）")
    p.add_argument("--thermal-iterations", type=int,
                   default=_CFG.get("thermal_erosion_iterations", 50),
                   help=f"熱侵蝕迭代次數（config 預設：{_CFG.get('thermal_erosion_iterations', 50)}）")
    p.add_argument("--thermal-talus", type=float,
                   default=_CFG.get("thermal_erosion_talus", 0.05),
                   help=f"熱侵蝕斜坡閾值，正規化 0-1（config 預設：{_CFG.get('thermal_erosion_talus', 0.05)}）")

    return p.parse_args()


_IMAGE_EXTS = ("*.png", "*.PNG", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG",
               "*.bmp", "*.BMP", "*.tif", "*.TIF", "*.tiff", "*.TIFF",
               "*.webp", "*.WEBP")


def _resolve_heightmap(args) -> Path | None:
    if args.heightmap:
        return Path(args.heightmap)
    hm_dir = Path(DEFAULT_HM_DIR)
    candidates = []
    for ext in _IMAGE_EXTS:
        candidates.extend(hm_dir.glob(ext))
    return sorted(candidates)[0] if candidates else None


def _resolve_origin_and_scale(args, image_path: Path | None):
    """
    Resolve args.x, args.z, args.scale from region_origin / region_size
    if not explicitly provided.  Mutates args in-place.
    """
    cfg_ro = _CFG.get("region_origin", [0, 0])
    cfg_rs = _CFG.get("region_size",   [2, 2])
    ro = args.region_origin if args.region_origin is not None else cfg_ro
    rs = args.region_size   if args.region_size   is not None else cfg_rs

    args.region_origin = ro
    args.region_size   = rs

    if args.x is None:
        args.x = ro[0] * 512
    if args.z is None:
        args.z = ro[1] * 512

    if args.scale is None:
        if image_path is not None and image_path.exists():
            from PIL import Image as _Img
            with _Img.open(image_path) as _im:
                img_w, img_h = _im.size
            block_w = rs[0] * 512
            block_h = rs[1] * 512
            scale_w = max(1, block_w // img_w) if img_w > 0 else 1
            scale_h = max(1, block_h // img_h) if img_h > 0 else 1
            args.scale = min(scale_w, scale_h)
        else:
            args.scale = 1


def _validate(args, image_path: Path | None) -> list[str]:
    errors = []

    if not args.preview_only:
        world = Path(args.world)
        if not world.exists():
            errors.append(f"存檔資料夾不存在：{world}")
        elif not (world / "region").exists():
            errors.append(f"找不到 region/ 子資料夾：{world}（這是有效的 Java Edition 存檔嗎？）")

    if image_path is None:
        errors.append(
            f"未指定 HeightMap 且 {DEFAULT_HM_DIR}/ 中沒有圖片檔案。"
            "請使用 --heightmap 指定圖片路徑。"
        )
    elif not image_path.exists():
        errors.append(f"HeightMap 圖片不存在：{image_path}")

    if not (-64 <= args.min_y <= 319):
        errors.append("--min-y 必須在 -64 到 319 之間")
    if not (-64 <= args.max_y <= 319):
        errors.append("--max-y 必須在 -64 到 319 之間")
    if args.min_y >= args.max_y:
        errors.append("--min-y 必須小於 --max-y")
    if args.scale is not None and args.scale < 1:
        errors.append("--scale 必須 ≥ 1")

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args       = _parse_args()
    image_path = _resolve_heightmap(args)
    _resolve_origin_and_scale(args, image_path)
    errors     = _validate(args, image_path)

    if errors:
        print("輸入錯誤：")
        for e in errors:
            print(f"  * {e}")
        sys.exit(1)

    verbose = not args.quiet

    if verbose:
        _print_banner(args, image_path)

    t_preview = 0.0
    t_apply   = 0.0

    biome_config = _CFG.get("biome_grid", None)
    # Load per-biome surface layer overrides from config (strip comment keys)
    biome_surface_layers: dict = {
        k: v for k, v in _CFG.get("biome_surface_layers", {}).items()
        if not k.startswith("_")
    }
    subsurface_layers: list = _CFG.get("subsurface_layers", [])
    biome_subsurface_layers: dict = {
        k: v for k, v in _CFG.get("biome_subsurface_layers", {}).items()
        if not k.startswith("_")
    }

    # ── Step 1: Preview ──────────────────────────────────────────────────
    if not args.no_preview:
        preview_path = str(Path(args.output) / "preview.png")
        if verbose:
            print("\n[1/2] 渲染地形預覽...")

        from heightmap_importer.preview import render_preview
        _t0 = time.perf_counter()
        render_preview(
            image_path  = str(image_path),
            min_y       = args.min_y,
            max_y       = args.max_y,
            sea_level   = args.sea_level,
            snow_line   = args.snow_line,
            scale       = args.scale,
            origin_x    = args.x,
            origin_z    = args.z,
            output_path = preview_path,
            open_after  = not args.no_open,
        )
        t_preview = time.perf_counter() - _t0

        # ── Biome editor ──────────────────────────────────────────────────
        if biome_config and biome_config.get("enabled", True) and not args.preview_only:
            from heightmap_importer.biome_editor import show_biome_editor
            import math as _math
            _rs = args.region_size
            _total_x = _rs[0] * 512
            _total_z = _rs[1] * 512
            _cell_size = biome_config.get("cell_size", 128)
            _cols = _math.ceil(_total_x / _cell_size)
            _rows = _math.ceil(_total_z / _cell_size)
            if verbose:
                print(f"\n  開啟生態域編輯器（{_cols}×{_rows} 格子）...")
            updated_grid = show_biome_editor(
                heightmap_path = str(image_path),
                total_x        = _total_x,
                total_z        = _total_z,
                cell_size      = _cell_size,
                initial_grid   = biome_config.get("grid", None),
                origin_x       = args.x,
                origin_z       = args.z,
                min_y          = args.min_y,
                max_y          = args.max_y,
                sea_level      = args.sea_level,
                snow_line      = args.snow_line,
                region_size    = _rs,
            )
            if updated_grid is not None:
                biome_config = dict(biome_config)
                biome_config["grid"] = updated_grid
                if verbose:
                    print("  生態域設定已更新。")

                # ── Surface layer editor (per-biome) ──────────────────────
                from heightmap_importer.biome_surface_editor import show_biome_surface_editor
                _unique_biomes = sorted({
                    b for row in updated_grid for b in row
                })
                _existing_bsl = _CFG.get("biome_surface_layers", {})
                # Remove the comment key before passing to editor
                _existing_bsl = {k: v for k, v in _existing_bsl.items()
                                  if not k.startswith("_")}
                _surface_layers_cfg = _CFG.get("surface_layers", None)
                if verbose:
                    print(f"\n  開啟表面方塊層編輯器（{len(_unique_biomes)} 個生態域）...")
                updated_bsl = show_biome_surface_editor(
                    selected_biomes          = _unique_biomes,
                    default_layers           = _surface_layers_cfg,
                    biome_surface_layers     = _existing_bsl,
                    min_y                    = args.min_y,
                    max_y                    = args.max_y,
                    dirt_top_replacement     = _CFG.get("dirt_top_replacement", True),
                    dirt_top_block           = _CFG.get("dirt_top_block", "minecraft:grass_block"),
                    subsurface_layers        = subsurface_layers,
                    biome_subsurface_layers  = biome_subsurface_layers,
                )
                if updated_bsl is not None:
                    dirt_top_replacement = updated_bsl.pop("_dirt_top_replacement", _CFG.get("dirt_top_replacement", True))
                    dirt_top_block       = updated_bsl.pop("_dirt_top_block",       _CFG.get("dirt_top_block", "minecraft:grass_block"))
                    _bsl_result          = updated_bsl.pop("_biome_subsurface_layers", {})
                    subsurface_layers    = _bsl_result.get("_default", subsurface_layers)
                    biome_subsurface_layers = {k: v for k, v in _bsl_result.items() if k != "_default"}
                    biome_surface_layers = updated_bsl
                    if verbose:
                        custom_count = len(biome_surface_layers)
                        print(f"  表面方塊層設定已更新（{custom_count} 個生態域已自訂）。")
                else:
                    if verbose:
                        print("  表面方塊層編輯器取消，沿用設定檔設定。")
            else:
                if verbose:
                    print("  生態域編輯器取消，沿用原始設定。")

        if args.preview_only:
            if verbose:
                print(f"\n  渲染耗時：{t_preview:.1f} 秒")
            print("\n(--preview-only 模式，不套用至存檔)")
            return

        # Confirmation prompt
        if not args.yes:
            print()
            try:
                ans = input("  是否將地形套用至 MC 存檔？[y/N]：").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n取消。")
                sys.exit(0)
            if ans not in ("y", "yes"):
                print("已取消。")
                sys.exit(0)

    # ── Step 2: Apply to world ───────────────────────────────────────────
    if verbose:
        step = "2/2" if not args.no_preview else "1/1"
        print(f"\n[{step}] 套用地形至 MC 存檔...")

    from heightmap_importer.importer import import_heightmap
    surface_layers        = _CFG.get("surface_layers", None)
    surface_depth_min     = _CFG.get("surface_depth_min", 1)
    surface_depth_max     = _CFG.get("surface_depth_max", 1)
    bedrock_floor         = _CFG.get("bedrock_floor", True)
    dirt_top_replacement  = _CFG.get("dirt_top_replacement", True)
    dirt_top_block        = _CFG.get("dirt_top_block", "minecraft:grass_block")
    # subsurface_layers already set above (may have been updated by biome editor)

    try:
        _t0 = time.perf_counter()
        import_heightmap(
            world_dir           = args.world,
            output_dir          = args.output,
            image_path          = str(image_path),
            origin_x            = args.x,
            origin_z            = args.z,
            min_y               = args.min_y,
            max_y               = args.max_y,
            sea_level           = args.sea_level,
            water_level         = args.water_level,
            surface_layers      = surface_layers,
            surface_depth_min   = surface_depth_min,
            surface_depth_max   = surface_depth_max,
            bedrock_floor         = bedrock_floor,
            scale                 = args.scale,
            dirt_top_replacement  = dirt_top_replacement,
            dirt_top_block        = dirt_top_block,
            verbose             = verbose,
            terrain_smoothing   = not args.no_terrain_smoothing,
            smooth_sigma        = args.smooth_sigma,
            smooth_passes       = args.smooth_passes,
            hydraulic_erosion   = not args.no_hydraulic_erosion,
            hydraulic_droplets  = args.hydraulic_droplets,
            thermal_erosion     = not args.no_thermal_erosion,
            thermal_iterations  = args.thermal_iterations,
            thermal_talus       = args.thermal_talus,
            biome_config              = biome_config,
            biome_surface_layers      = biome_surface_layers,
            subsurface_layers         = subsurface_layers,
            biome_subsurface_layers   = biome_subsurface_layers,
        )
        t_apply = time.perf_counter() - _t0
    except KeyboardInterrupt:
        print("\n使用者中斷。")
        sys.exit(1)
    except Exception as exc:
        print(f"\n錯誤：{exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if verbose:
        print(f"\n完成！請在 Minecraft 1.21.1 中開啟 '{args.output}' 資料夾中的存檔。")
        print()
        print("─" * 40)
        if t_preview > 0:
            print(f"  渲染預覽：{t_preview:6.1f} 秒")
        print(f"  套用地形：{t_apply:6.1f} 秒")
        if t_preview > 0:
            print(f"  總計    ：{t_preview + t_apply:6.1f} 秒")
        print("─" * 40)


def _print_banner(args, image_path):
    ro = args.region_origin
    rs = args.region_size
    print("=" * 64)
    print("  MCMap – HeightMap → Minecraft 1.21.1 World Importer")
    print("=" * 64)
    print(f"  輸入存檔  : {args.world}")
    print(f"  HeightMap : {image_path}")
    print(f"  輸出資料夾: {args.output}")
    print(f"  Region 起點: r.{ro[0]}.{ro[1]}  大小: {rs[0]}×{rs[1]} regions ({rs[0]*512}×{rs[1]*512} 格)")
    print(f"  起始座標  : X={args.x}, Z={args.z}")
    print(f"  Y 範圍    : {args.min_y} ~ {args.max_y}")
    print(f"  海平面    : Y={args.sea_level}  （預覽用）")
    print(f"  水面      : Y={args.water_level}  （低於此高度填水）")
    # Show surface layers from config
    layers = _CFG.get("surface_layers", None)
    if layers:
        print("  表面方塊層：")
        for lyr in sorted(layers, key=lambda l: l["max_y"], reverse=True):
            blend_str = f"  模糊 {lyr['blend']} 格" if lyr.get("blend", 0) > 0 else ""
            print(f"    Y {lyr['min_y']:>4} ~ {lyr['max_y']:<4}  {lyr['block']}{blend_str}")
    print(f"  表面方塊深度: {_CFG.get('surface_depth_min', 1)}～{_CFG.get('surface_depth_max', 1)} 格（坡度+雜訊動態調整）")
    print(f"  縮放比例  : {args.scale} 格/像素")
    print(f"  地形平滑  : {'開啟' if not args.no_terrain_smoothing else '關閉'}"
          + (f"（sigma={args.smooth_sigma}, {args.smooth_passes} 次）" if not args.no_terrain_smoothing else ""))
    print(f"  水力侵蝕  : {'開啟' if not args.no_hydraulic_erosion else '關閉'}"
          + (f"（雨滴 {args.hydraulic_droplets}）" if not args.no_hydraulic_erosion else ""))
    print(f"  熱侵蝕    : {'開啟' if not args.no_thermal_erosion else '關閉'}"
          + (f"（迭代 {args.thermal_iterations}，talus {args.thermal_talus}）" if not args.no_thermal_erosion else ""))
    _bg = _CFG.get("biome_grid", None)
    if _bg and _bg.get("enabled", True):
        _grid = _bg.get("grid", None)
        _rows = len(_grid) if _grid else "?"
        _cols = len(_grid[0]) if _grid else "?"
        _blend = f"，混合半徑 {_bg.get('blend_radius', 8)} 格" if _bg.get("blend_enabled", False) else ""
        print(f"  生態域網格: 開啟（格子大小 {_bg.get('cell_size', 128)} 格，{_rows}×{_cols} 格子{_blend}）")
    else:
        print(f"  生態域網格: 關閉（全部 minecraft:plains）")
    print("-" * 64)


if __name__ == "__main__":
    main()
