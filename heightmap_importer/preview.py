"""
地形預覽渲染器

基於 HeightMap 圖片，在套用至 MC 存檔前，先輸出：
  - 左圖：3D 表面圖（含光照）
  - 右圖：俯視光照圖（hillshade）

輸出為 PNG 檔。顏色依高度（相對海平面）映射：
  深海 → 淺海 → 沙灘 → 草地 → 森林 → 岩石 → 雪地
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from . import color_config as _cc


def _build_color_anchors(
    sea_level: int, snow_line: int
) -> list[tuple[float, tuple[float, float, float]]]:
    """
    Build colour anchors for a green→red heatmap.
    Parameters are loaded from terrain_colors.json (falls back to built-in
    defaults when the file is absent).

    sea_level / snow_line are accepted for API compatibility but unused.
    """
    cfg        = _cc.load()
    hm         = cfg["heatmap"]
    wb         = cfg["world_bounds"]

    _GREEN     = tuple(hm["green"])
    _RED       = tuple(hm["red"])
    world_min  = wb["min_y"]
    world_max  = wb["max_y"]
    green_top  = hm["green_zone_top_y"]
    red_bot    = hm["red_zone_bot_y"]
    step       = hm["anchor_step_blocks"]

    anchors: list[tuple[int, tuple[float, float, float]]] = [
        (world_min, _GREEN),   # 最低點：純綠
        (green_top, _GREEN),   # 純綠區頂端（漸層起點）
    ]

    grad_range = red_bot - green_top
    y = green_top + step
    while y < red_bot:
        t = (y - green_top) / grad_range
        r = min(1.0, 2.0 * t)
        g = min(1.0, 2.0 * (1.0 - t))
        anchors.append((y, (r, g, 0.0)))
        y += step

    anchors.append((red_bot,   _RED))   # 純紅區起點
    anchors.append((world_max, _RED))   # 最高點

    return anchors


def _height_to_colors(
    heights: np.ndarray, sea_level: int, snow_line: int
) -> np.ndarray:
    """
    Vectorised height→RGB mapping.

    Mode is read from terrain_colors.json:
      'stepped'  – discrete colour bands (sharp boundaries)
      'gradient' – smooth linear interpolation between anchors

    Returns np.ndarray shape (H, W, 3), float32, values in [0, 1].
    """
    cfg  = _cc.load()
    mode = cfg.get("mode", "stepped")

    if mode == "stepped":
        bands = sorted(cfg["color_bands"], key=lambda b: b["min_y"])
        out   = np.full((*heights.shape, 3), _cc.to_rgb_float(bands[0]["color"]), dtype=np.float32)
        for band in bands[1:]:
            mask = heights >= band["min_y"]
            if np.any(mask):
                out[mask] = np.array(_cc.to_rgb_float(band["color"]), dtype=np.float32)
        return np.clip(out, 0.0, 1.0)

    # ── gradient mode ──────────────────────────────────────────────────────
    anchors = _build_color_anchors(sea_level, snow_line)
    out     = np.zeros((*heights.shape, 3), dtype=np.float32)
    out[:, :] = anchors[0][1]

    for i in range(len(anchors) - 1):
        y0, c0 = anchors[i]
        y1, c1 = anchors[i + 1]
        span = y1 - y0
        if span <= 0:
            continue
        mask = (heights >= y0) & (heights < y1)
        if not np.any(mask):
            continue
        t = np.clip((heights[mask] - y0) / span, 0.0, 1.0)
        for ch in range(3):
            out[mask, ch] = c0[ch] + (c1[ch] - c0[ch]) * t

    out[heights >= anchors[-1][0]] = anchors[-1][1]
    return np.clip(out, 0.0, 1.0)


def _load_height_array(image_path: str, min_y: int, max_y: int,
                       max_size: int) -> np.ndarray:
    """Load grayscale image, optionally downsample, map to Y coords."""
    img = Image.open(image_path)

    # 16-bit PNG support
    if img.mode in ("I;16", "I"):
        arr = np.array(img, dtype=np.float64)
        arr = arr / (arr.max() or 1.0)
    else:
        img = img.convert("L")
        arr = np.array(img, dtype=np.float64) / 255.0

    # Downsample if too large for comfortable rendering
    h, w = arr.shape
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img_resized = Image.fromarray((arr * 255).astype(np.uint8), mode="L")
        img_resized = img_resized.resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img_resized, dtype=np.float64) / 255.0

    return (min_y + (max_y - min_y) * arr).astype(np.float32)


def _try_cjk_font():
    """Try to set a CJK-compatible font for matplotlib."""
    import matplotlib
    for name in ["Microsoft JhengHei", "Microsoft YaHei", "SimHei",
                 "Noto Sans CJK TC", "Noto Sans TC"]:
        try:
            matplotlib.rcParams["font.sans-serif"] = (
                [name] + matplotlib.rcParams["font.sans-serif"]
            )
            break
        except Exception:
            continue
    matplotlib.rcParams["axes.unicode_minus"] = False


def render_preview(
    image_path:  str,
    min_y:       int,
    max_y:       int,
    sea_level:   int,
    snow_line:   int,
    scale:       int  = 1,
    origin_x:    int  = 0,
    origin_z:    int  = 0,
    output_path: str  = "output/preview.png",
    open_after:  bool = True,
) -> str:
    """
    Render a dual-panel terrain preview and save to PNG.

    Left  panel: 3D surface plot with LightSource shading.
    Right panel: 2D top-down hillshade view.

    Parameters
    ----------
    image_path  : Path to the grayscale heightmap image.
    min_y       : MC Y for pixel value 0.
    max_y       : MC Y for pixel value 255.
    sea_level   : Y boundary for water/land colour split (blue contour).
    snow_line   : Y above which the surface becomes snow (white contour).
    scale       : MC blocks per pixel (used only in title info).
    origin_x/z  : World coordinates shown in title.
    output_path : Where to save the PNG.
    open_after  : Try to open the PNG with the system viewer.

    Returns
    -------
    str  Path to the saved PNG.
    """
    import matplotlib
    matplotlib.use("Agg")           # non-interactive backend → file output
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, LinearSegmentedColormap

    _try_cjk_font()

    # --- Load height arrays (two resolutions) ---
    h_3d = _load_height_array(image_path, min_y, max_y, max_size=256)
    h_2d = _load_height_array(image_path, min_y, max_y, max_size=512)

    rows_3d, cols_3d = h_3d.shape
    rows_2d, cols_2d = h_2d.shape

    img_w = int(cols_2d / (h_2d.shape[0] / h_2d.shape[1])) if h_2d.shape[0] else cols_2d
    orig_img  = Image.open(image_path)
    orig_w, orig_h = orig_img.width, orig_img.height
    mc_w = orig_w * scale
    mc_h = orig_h * scale

    # --- Colour arrays ---
    colors_3d = _height_to_colors(h_3d, sea_level, snow_line)
    colors_2d = _height_to_colors(h_2d, sea_level, snow_line)

    # --- LightSource shading ---
    ls = LightSource(azdeg=315, altdeg=45)

    h_norm_3d = (h_3d - h_3d.min()) / max(h_3d.max() - h_3d.min(), 1e-6)
    h_norm_2d = (h_2d - h_2d.min()) / max(h_2d.max() - h_2d.min(), 1e-6)

    shaded_3d = ls.shade_rgb(colors_3d, h_norm_3d, vert_exag=2, blend_mode="soft")
    shaded_2d = ls.shade_rgb(colors_2d, h_norm_2d, vert_exag=2, blend_mode="soft")

    # --- Terrain colormap (for 3D surface) ---
    h_range = max_y - min_y or 1

    def _norm(y: float) -> float:
        return max(0.0, min(1.0, (y - min_y) / h_range))

    _cfg  = _cc.load()
    _mode = _cfg.get("mode", "stepped")

    if _mode == "stepped":
        # Build a stepped colormap: duplicate each colour at band boundary
        # with an epsilon offset so transitions are sharp, not blended.
        _bands     = sorted(_cfg["color_bands"], key=lambda b: b["min_y"])
        _eps       = 1e-5
        _cmap_pts  = [(0.0, tuple(_bands[0]["color"]))]
        for _i, _band in enumerate(_bands):
            _pos = _norm(_band["min_y"])
            _col = tuple(_cc.to_rgb_float(_band["color"]))
            if _pos > _cmap_pts[-1][0] + _eps:
                _cmap_pts.append((_pos - _eps, _cmap_pts[-1][1]))
            if _pos > _cmap_pts[-1][0]:
                _cmap_pts.append((_pos, _col))
            else:
                _cmap_pts[-1] = (_cmap_pts[-1][0], _col)
        if _cmap_pts[-1][0] < 1.0:
            _cmap_pts.append((1.0, _cmap_pts[-1][1]))
        terrain_cmap = LinearSegmentedColormap.from_list("terrain_mc", _cmap_pts)
    else:
        raw_anchors  = _build_color_anchors(sea_level, snow_line)
        cmap_anchors = [(0.0, raw_anchors[0][1])]
        for y_val, col in raw_anchors:
            pos = _norm(y_val)
            if pos > cmap_anchors[-1][0]:
                cmap_anchors.append((pos, col))
        if cmap_anchors[-1][0] < 1.0:
            cmap_anchors.append((1.0, raw_anchors[-1][1]))
        terrain_cmap = LinearSegmentedColormap.from_list(
            "terrain_mc", [(p, c) for p, c in cmap_anchors]
        )

    # --- Figure ---
    fig = plt.figure(figsize=(16, 7))
    fig.patch.set_facecolor("#1a1a2e")

    title = (
        f"地形預覽  |  圖片 {orig_w}×{orig_h} px  →  MC {mc_w}×{mc_h} 格  |  "
        f"Y 範圍 {min_y}~{max_y}  |  海平面 Y={sea_level}  |  雪線 Y={snow_line}  |  "
        f"起始 ({origin_x}, {origin_z})"
    )
    fig.suptitle(title, fontsize=10, color="white")

    # ── Left: 3D surface ──────────────────────────────────────────────────
    ax3d = fig.add_subplot(121, projection="3d")
    ax3d.set_facecolor("#0d0d1a")

    X3d = np.arange(cols_3d)
    Z3d = np.arange(rows_3d)
    Xg, Zg = np.meshgrid(X3d, Z3d)
    face_colors = terrain_cmap(h_norm_3d)   # (R, C, 4)
    # Blend with LightSource for 3D shading
    face_colors[:, :, :3] = shaded_3d

    ax3d.plot_surface(
        Xg, Zg, h_3d,
        facecolors=face_colors,
        rstride=1, cstride=1,
        linewidth=0, antialiased=False,
        shade=False,
    )
    ax3d.set_xlabel("X", color="white")
    ax3d.set_ylabel("Z", color="white")
    ax3d.set_zlabel("Y (高度)", color="white")
    ax3d.set_title("3D 地形", color="white", pad=8)
    ax3d.tick_params(colors="white")
    ax3d.xaxis.pane.fill = ax3d.yaxis.pane.fill = ax3d.zaxis.pane.fill = False
    ax3d.view_init(elev=35, azim=-60)

    # Reference planes: sea level (blue) and snow line (white)
    for ref_y, ref_color, ref_alpha in [
        (sea_level, "royalblue", 0.15),
        (snow_line, "white",     0.10),
    ]:
        if min_y <= ref_y <= max_y:
            sx = np.array([[0, cols_3d - 1], [0, cols_3d - 1]])
            sz = np.array([[0, 0], [rows_3d - 1, rows_3d - 1]])
            sy = np.full_like(sx, ref_y, dtype=float)
            ax3d.plot_surface(sx, sz, sy, alpha=ref_alpha,
                              color=ref_color, shade=False)

    # ── Right: 2D top-down hillshade ──────────────────────────────────────
    ax2d = fig.add_subplot(122)
    ax2d.set_facecolor("#0d0d1a")

    ax2d.imshow(shaded_2d, origin="upper", aspect="equal", interpolation="bilinear")

    # Contour lines: sea level (blue) and snow line (white)
    contour_levels, contour_colors = [], []
    if h_2d.min() < sea_level < h_2d.max():
        contour_levels.append(sea_level)
        contour_colors.append("royalblue")
    if h_2d.min() < snow_line < h_2d.max():
        contour_levels.append(snow_line)
        contour_colors.append("white")
    if contour_levels:
        ax2d.contour(h_2d, levels=contour_levels,
                     colors=contour_colors, linewidths=0.8, alpha=0.8)

    ax2d.set_title("俯視光照圖（藍線=海平面  白線=雪線）", color="white", pad=8)
    ax2d.set_xlabel("X（像素）", color="white")
    ax2d.set_ylabel("Z（像素）", color="white")
    ax2d.tick_params(colors="white")

    # Simple colorbar for elevation
    sm = plt.cm.ScalarMappable(
        cmap=terrain_cmap,
        norm=plt.Normalize(vmin=min_y, vmax=max_y)
    )
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax2d, fraction=0.03, pad=0.02)
    cbar.set_label("高度 Y", color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    # --- Save ---
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  預覽圖已儲存：{out.resolve()}")

    # --- Open with system viewer ---
    if open_after:
        _open_file(str(out.resolve()))

    return str(out)


def _open_file(path: str):
    """Open a file with the OS default application."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass  # silently ignore if OS open fails
