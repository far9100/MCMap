"""
Interactive Biome Grid Editor for MCMap.

PIL/numpy image-based rendering for large grids.
Two editing modes:
  - Normal  : one click paints a 16×16 MC-block area (1 "chunk").
  - Detail  : click a chunk on the main canvas to open a 2×2-block-per-cell
              sub-grid in the right panel for fine-grained editing.
"""

import math
import tkinter as tk

import numpy as np
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Biome colour palette
# ---------------------------------------------------------------------------

BIOME_COLORS: dict[str, str] = {
    "minecraft:plains":                   "#7CCC6C",
    "minecraft:forest":                   "#3A7D44",
    "minecraft:birch_forest":             "#55BB55",
    "minecraft:dark_forest":              "#205830",
    "minecraft:taiga":                    "#2D6E7E",
    "minecraft:snowy_taiga":              "#3A8A9E",
    "minecraft:snowy_plains":             "#CCE8F4",
    "minecraft:desert":                   "#D9C07A",
    "minecraft:savanna":                  "#C8B454",
    "minecraft:savanna_plateau":          "#B8A040",
    "minecraft:jungle":                   "#1E8C45",
    "minecraft:sparse_jungle":            "#4CAF50",
    "minecraft:bamboo_jungle":            "#2E9E50",
    "minecraft:swamp":                    "#4D6B3C",
    "minecraft:mangrove_swamp":           "#3A5E35",
    "minecraft:badlands":                 "#C0603A",
    "minecraft:eroded_badlands":          "#D0704A",
    "minecraft:wooded_badlands":          "#A0502A",
    "minecraft:ocean":                    "#3D6FA6",
    "minecraft:deep_ocean":               "#1A3D6B",
    "minecraft:frozen_ocean":             "#A0C8E0",
    "minecraft:deep_frozen_ocean":        "#8090A0",
    "minecraft:cold_ocean":               "#2A5A8A",
    "minecraft:lukewarm_ocean":           "#4A90C0",
    "minecraft:warm_ocean":               "#5AAAD0",
    "minecraft:beach":                    "#D4C07A",
    "minecraft:snowy_beach":              "#E0E8F0",
    "minecraft:stony_shore":              "#909090",
    "minecraft:windswept_hills":          "#8A8A8A",
    "minecraft:windswept_gravelly_hills": "#7A7A7A",
    "minecraft:windswept_forest":         "#6A8A6A",
    "minecraft:windswept_savanna":        "#C0AA44",
    "minecraft:meadow":                   "#AAD56C",
    "minecraft:frozen_river":             "#A0D0E8",
    "minecraft:river":                    "#5088C0",
    "minecraft:mushroom_fields":          "#CC88BB",
    "minecraft:ice_spikes":               "#B8D8F0",
    "minecraft:cherry_grove":             "#F4A0C0",
    "minecraft:grove":                    "#6090A0",
    "minecraft:snowy_slopes":             "#D0E0F0",
    "minecraft:jagged_peaks":             "#C8C8C8",
    "minecraft:frozen_peaks":             "#D0E8F8",
    "minecraft:stony_peaks":              "#A0A0A0",
    "minecraft:lush_caves":               "#44BB44",
    "minecraft:dripstone_caves":          "#A09060",
    "minecraft:deep_dark":                "#202830",
    "minecraft:nether_wastes":            "#CC3300",
    "minecraft:soul_sand_valley":         "#7A6050",
    "minecraft:crimson_forest":           "#CC2244",
    "minecraft:warped_forest":            "#22AAAA",
    "minecraft:basalt_deltas":            "#605050",
    "minecraft:the_end":                  "#DDDDAA",
    "minecraft:small_end_islands":        "#CCCC99",
    "minecraft:end_midlands":             "#CCCC88",
    "minecraft:end_highlands":            "#CCCC77",
    "minecraft:end_barrens":              "#BBBB66",
    "minecraft:the_void":                 "#111111",
}

_FALLBACK_COLOR = "#888888"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------------------
# Terrain background  (same colour anchors + hillshading as preview.py)
# ---------------------------------------------------------------------------

def _build_terrain_anchors(
    sea_level: int, snow_line: int
) -> list[tuple[float, tuple[float, float, float]]]:
    """Exact replica of preview.py _build_color_anchors (Y → RGB in [0,1])."""
    mid        = (snow_line - sea_level) // 2
    rock_start = sea_level + max(mid - 10, 5)
    return [
        (sea_level - 100, (0.08, 0.15, 0.45)),   # 深海
        (sea_level -   5, (0.15, 0.35, 0.65)),   # 淺海
        (sea_level,       (0.20, 0.45, 0.70)),   # 海平面
        (sea_level +   4, (0.82, 0.78, 0.58)),   # 沙灘
        (sea_level +  12, (0.42, 0.68, 0.25)),   # 草地
        (rock_start,      (0.20, 0.48, 0.14)),   # 森林
        (snow_line -  15, (0.55, 0.52, 0.46)),   # 碎石坡
        (snow_line,       (0.94, 0.95, 0.97)),   # 雪線
    ]


def _generate_terrain_image(
    heightmap_path: str,
    canvas_w: int,
    canvas_h: int,
    sea_level: int,
    snow_line: int,
    min_y: int,
    max_y: int,
) -> np.ndarray:
    """
    Return (H, W, 3) float32 in [0, 255] matching preview.py appearance:
    same colour anchors (absolute MC Y) + numpy hillshading.
    """
    with Image.open(heightmap_path) as hm:
        gray = hm.convert("L").resize((canvas_w, canvas_h), Image.LANCZOS)

    # Pixel value → absolute MC Y
    h_mc = (np.asarray(gray, dtype=np.float32) / 255.0) * (max_y - min_y) + min_y

    # ── Colour from anchors ───────────────────────────────────────────────
    anchors = _build_terrain_anchors(sea_level, snow_line)
    rgb = np.zeros((canvas_h, canvas_w, 3), dtype=np.float32)
    rgb[:] = anchors[0][1]   # fill with below-minimum colour

    for i in range(len(anchors) - 1):
        y0, c0 = anchors[i]
        y1, c1 = anchors[i + 1]
        if y1 <= y0:
            continue
        mask = (h_mc >= y0) & (h_mc < y1)
        if not mask.any():
            continue
        t = ((h_mc[mask] - y0) / (y1 - y0)).reshape(-1, 1)
        rgb[mask] = np.array(c0, dtype=np.float32) * (1 - t) + \
                    np.array(c1, dtype=np.float32) * t

    rgb[h_mc >= anchors[-1][0]] = anchors[-1][1]

    # ── Hillshading (mirrors LightSource azdeg=315, altdeg=45, soft) ────
    h_norm = (h_mc - h_mc.min()) / max(float(h_mc.max() - h_mc.min()), 1e-6)
    dy, dx  = np.gradient(h_norm)

    az  = 315.0 * np.pi / 180.0
    alt =  45.0 * np.pi / 180.0
    lx  = np.cos(alt) * np.cos(az)
    ly  = np.cos(alt) * np.sin(az)
    lz  = np.sin(alt)

    vert_exag = 2.0
    nx = -dx * vert_exag
    ny = -dy * vert_exag
    nz = np.ones_like(nx)
    n_mag = np.sqrt(nx**2 + ny**2 + nz**2)
    intensity = ((nx * lx + ny * ly + nz * lz) / n_mag).clip(0.0, 1.0)

    # Soft-light blend (Photoshop / matplotlib soft mode)
    I = intensity[:, :, np.newaxis]   # (H, W, 1)
    c = rgb.clip(0.0, 1.0)
    shaded = np.where(
        I <= 0.5,
        2.0 * c * I + c ** 2 * (1.0 - 2.0 * I),
        2.0 * c * (1.0 - I) + np.sqrt(c.clip(1e-8)) * (2.0 * I - 1.0),
    )

    return (shaded.clip(0.0, 1.0) * 255.0).astype(np.float32)


# ---------------------------------------------------------------------------
# Composite renderer
# ---------------------------------------------------------------------------

def _render_composite(
    bg_arr:          np.ndarray,
    grid_idx:        np.ndarray,
    color_palette:   np.ndarray,
    canvas_w:        int,
    canvas_h:        int,
    cols:            int,
    rows:            int,
    show_grid_lines: bool,
) -> np.ndarray:
    """Blend terrain + biome colour overlay → (H, W, 3) uint8."""
    y_idx = (np.arange(canvas_h) * rows / canvas_h).astype(np.int32).clip(0, rows - 1)
    x_idx = (np.arange(canvas_w) * cols / canvas_w).astype(np.int32).clip(0, cols - 1)
    grid_colors = color_palette[grid_idx[y_idx[:, None], x_idx[None, :]]].astype(np.float32)
    composite = (bg_arr * 0.5 + grid_colors * 0.5).clip(0, 255).astype(np.uint8)

    if show_grid_lines:
        boost = 55
        for gz in range(1, rows):
            y = int(gz * canvas_h / rows)
            if 0 <= y < canvas_h:
                composite[y] = np.clip(composite[y].astype(np.int32) + boost, 0, 255)
        for gx in range(1, cols):
            x = int(gx * canvas_w / cols)
            if 0 <= x < canvas_w:
                composite[:, x] = np.clip(composite[:, x].astype(np.int32) + boost, 0, 255)
    return composite


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# One "chunk" in the editor = 16 MC blocks square (same as a Minecraft chunk).
_CHUNK_BLOCKS = 16


def show_biome_editor(
    heightmap_path: str,
    total_x:        int,
    total_z:        int,
    cell_size:      int,
    initial_grid:   "list[list[str]] | None",
    origin_x:       int,
    origin_z:       int,
    min_y:          int,
    max_y:          int,
    sea_level:      int,
    snow_line:      int = 192,
) -> "list[list[str]] | None":
    """
    Display the interactive biome grid editor.

    Normal mode  – click / drag paints a full 16×16 MC-block area at once.
    Detail mode  – click a chunk on the main canvas to open an 8×8 sub-grid
                   (cell_size=2 ⟹ each sub-cell = 2×2 MC blocks).

    Returns updated grid on confirm, None on cancel / close.
    """
    # Grid dimensions (in biome cells)
    cols = math.ceil(total_x / max(1, cell_size))
    rows = math.ceil(total_z / max(1, cell_size))

    # How many grid cells fit in one 16-block chunk
    cells_per_chunk = max(1, _CHUNK_BLOCKS // cell_size)

    result: "list[list[str]] | None" = None

    # ── Tkinter root ─────────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("MCMap – 生態域視覺化編輯器")
    root.resizable(False, False)
    root.configure(bg="#2B2B2B")
    root.withdraw()

    PANEL_W  = 220
    CHROME_H = 60
    CHROME_W = PANEL_W + 40

    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()
    avail_w = int(scr_w * 0.85) - CHROME_W
    avail_h = int(scr_h * 0.85) - CHROME_H

    aspect = total_x / max(1, total_z)
    if aspect >= 1.0:
        canvas_w = avail_w
        canvas_h = int(canvas_w / aspect)
        if canvas_h > avail_h:
            canvas_h = avail_h
            canvas_w = int(canvas_h * aspect)
    else:
        canvas_h = avail_h
        canvas_w = int(canvas_h * aspect)
        if canvas_w > avail_w:
            canvas_w = avail_w
            canvas_h = int(canvas_w / aspect)

    canvas_w = max(canvas_w, cols * 2, 200)
    canvas_h = max(canvas_h, rows * 2, 200)

    cell_w = canvas_w / max(1, cols)
    cell_h = canvas_h / max(1, rows)
    show_grid_lines = cell_w >= 6 and cell_h >= 6

    # ── Colour palette ───────────────────────────────────────────────────────
    all_biomes    = sorted(BIOME_COLORS.keys())
    biome_to_idx  = {b: i for i, b in enumerate(all_biomes)}
    fallback_idx  = len(all_biomes)
    color_palette = np.array(
        [_hex_to_rgb(BIOME_COLORS[b]) for b in all_biomes]
        + [_hex_to_rgb(_FALLBACK_COLOR)],
        dtype=np.uint8,
    )

    # ── Working grid ─────────────────────────────────────────────────────────
    grid: list[list[str]] = []
    for r in range(rows):
        row: list[str] = []
        for c in range(cols):
            if initial_grid and r < len(initial_grid) and c < len(initial_grid[r]):
                row.append(initial_grid[r][c])
            else:
                row.append("minecraft:plains")
        grid.append(row)

    grid_idx = np.array(
        [biome_to_idx.get(grid[gz][gx], fallback_idx)
         for gz in range(rows) for gx in range(cols)],
        dtype=np.int16,
    ).reshape(rows, cols)

    # ── Terrain background (float32) ─────────────────────────────────────────
    try:
        bg_arr = _generate_terrain_image(
            heightmap_path, canvas_w, canvas_h, sea_level, snow_line, min_y, max_y
        )
    except Exception:
        bg_arr = np.full((canvas_h, canvas_w, 3), [70, 100, 60], dtype=np.float32)

    # ── Main layout ──────────────────────────────────────────────────────────
    main_frame = tk.Frame(root, bg="#2B2B2B")
    main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # Left: main canvas
    left_frame = tk.Frame(main_frame, bg="#2B2B2B")
    left_frame.pack(side=tk.LEFT, padx=(0, 8))

    canvas = tk.Canvas(
        left_frame,
        width=canvas_w, height=canvas_h,
        bg="#1A1A1A", bd=1, relief=tk.SUNKEN,
        cursor="crosshair", highlightthickness=0,
    )
    canvas.pack()

    tk.Label(
        left_frame,
        text=f"格子大小：{cell_size} 格  共 {cols}×{rows} 格  "
             f"（每次點選 = {_CHUNK_BLOCKS}×{_CHUNK_BLOCKS} MC 格）",
        bg="#2B2B2B", fg="#AAAAAA", font=("Consolas", 9),
    ).pack(pady=(4, 0))

    # Right: panel
    right_frame = tk.Frame(main_frame, bg="#2B2B2B", width=PANEL_W)
    right_frame.pack(side=tk.LEFT, fill=tk.Y)
    right_frame.pack_propagate(False)

    # ── Current selection ─────────────────────────────────────────────────────
    tk.Label(
        right_frame, text="─ 目前選擇 ─",
        bg="#2B2B2B", fg="#CCCCCC", font=("Consolas", 9, "bold"),
    ).pack(pady=(0, 2))

    current_label = tk.Label(
        right_frame, text="■ plains",
        bg="#2B2B2B", fg=BIOME_COLORS.get("minecraft:plains", "#7CCC6C"),
        font=("Consolas", 9), relief=tk.GROOVE, anchor=tk.W, padx=6, pady=4,
    )
    current_label.pack(fill=tk.X, padx=4, pady=(0, 6))

    # ── Biome listbox ────────────────────────────────────────────────────────
    tk.Label(
        right_frame, text="─ 所有生態域 ─",
        bg="#2B2B2B", fg="#CCCCCC", font=("Consolas", 9, "bold"),
    ).pack(pady=(0, 2))

    list_frame = tk.Frame(right_frame, bg="#2B2B2B")
    list_frame.pack(fill=tk.BOTH, expand=True, padx=4)

    scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    listbox = tk.Listbox(
        list_frame,
        yscrollcommand=scrollbar.set,
        bg="#1A1A1A", fg="#DDDDDD",
        selectbackground="#4A6A9A", selectforeground="#FFFFFF",
        font=("Consolas", 9), activestyle="none",
        bd=0, highlightthickness=0,
    )
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=listbox.yview)

    for b in all_biomes:
        listbox.insert(tk.END, "  " + b.replace("minecraft:", ""))

    # ── Detail mode section ──────────────────────────────────────────────────
    tk.Frame(right_frame, bg="#555555", height=1).pack(fill=tk.X, padx=4, pady=4)

    detail_header = tk.Frame(right_frame, bg="#2B2B2B")
    detail_header.pack(fill=tk.X, padx=4)

    tk.Label(
        detail_header, text="─ 區塊細節 ─",
        bg="#2B2B2B", fg="#CCCCCC", font=("Consolas", 9, "bold"),
    ).pack(side=tk.LEFT)

    detail_enabled = tk.BooleanVar(value=False)

    detail_check = tk.Checkbutton(
        right_frame, text=f"啟用（每格 = {cell_size}×{cell_size} MC 格）",
        variable=detail_enabled,
        bg="#2B2B2B", fg="#CCCCCC",
        selectcolor="#1A1A1A", activebackground="#2B2B2B",
        font=("Consolas", 8),
    )
    detail_check.pack(anchor=tk.W, padx=4)

    # Sub-editor frame (hidden until detail mode is enabled)
    sub_frame = tk.Frame(right_frame, bg="#2B2B2B")
    # (packed / forgotten by on_detail_toggle)

    sub_info_label = tk.Label(
        sub_frame,
        text="點選左側地圖以選擇區塊",
        bg="#2B2B2B", fg="#888888", font=("Consolas", 8),
    )
    sub_info_label.pack(pady=(2, 2))

    # Sub-canvas: cells_per_chunk × cells_per_chunk grid
    SUB_CELL_PX   = max(8, (PANEL_W - 20) // cells_per_chunk)
    SUB_CANVAS_PX = SUB_CELL_PX * cells_per_chunk

    sub_canvas = tk.Canvas(
        sub_frame,
        width=SUB_CANVAS_PX, height=SUB_CANVAS_PX,
        bg="#1A1A1A", highlightthickness=1, highlightbackground="#555555",
        cursor="crosshair",
    )
    sub_canvas.pack(pady=(0, 4))

    sub_photo_ref  = [None]   # keep PhotoImage alive
    sub_canvas_img = sub_canvas.create_image(0, 0, anchor=tk.NW, tags="sub_bg")

    # ── Confirm / Cancel buttons ─────────────────────────────────────────────
    tk.Frame(right_frame, bg="#555555", height=1).pack(fill=tk.X, padx=4, pady=4)

    selected_biome = ["minecraft:plains"]

    def _show_confirm_preview() -> None:
        """Open a modal preview window showing the biome map for final confirmation."""
        preview_win = tk.Toplevel(root)
        preview_win.title("MCMap – 確認生態域配置")
        preview_win.configure(bg="#2B2B2B")
        preview_win.resizable(False, False)
        preview_win.grab_set()   # modal – block main editor

        # Scale preview to fit within 700×700 while keeping aspect ratio
        max_px   = 700
        scale    = min(max_px / max(canvas_w, 1), max_px / max(canvas_h, 1), 1.0)
        pw       = max(int(canvas_w * scale), cols * 2, 200)
        ph       = max(int(canvas_h * scale), rows * 2, 200)

        # Pure biome-colour map (no terrain blend) so every cell colour is unambiguous
        y_idx_p  = (np.arange(ph) * rows / ph).astype(np.int32).clip(0, rows - 1)
        x_idx_p  = (np.arange(pw) * cols / pw).astype(np.int32).clip(0, cols - 1)
        arr      = color_palette[grid_idx[y_idx_p[:, None], x_idx_p[None, :]]].astype(np.uint8)

        # Grid lines when cells are large enough
        if pw / max(cols, 1) >= 4 and ph / max(rows, 1) >= 4:
            boost = 55
            for gz in range(1, rows):
                y = int(gz * ph / rows)
                if 0 <= y < ph:
                    arr[y] = np.clip(arr[y].astype(np.int32) + boost, 0, 255)
            for gx in range(1, cols):
                x = int(gx * pw / cols)
                if 0 <= x < pw:
                    arr[:, x] = np.clip(arr[:, x].astype(np.int32) + boost, 0, 255)

        img   = Image.fromarray(arr, "RGB")
        photo = ImageTk.PhotoImage(img)

        img_label       = tk.Label(preview_win, image=photo, bg="#1A1A1A",
                                   bd=1, relief=tk.SUNKEN)
        img_label.image = photo          # keep reference alive
        img_label.pack(padx=8, pady=(8, 4))

        tk.Label(
            preview_win,
            text=f"生態域預覽  {cols}×{rows} 格  ── 請確認配置是否正確",
            bg="#2B2B2B", fg="#AAAAAA", font=("Consolas", 9),
        ).pack(pady=(0, 6))

        pb_frame = tk.Frame(preview_win, bg="#2B2B2B")
        pb_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        def on_reedit() -> None:
            preview_win.destroy()            # simply close preview; main editor stays open

        def on_done() -> None:
            nonlocal result
            result = [row[:] for row in grid]
            preview_win.destroy()
            root.destroy()

        tk.Button(
            pb_frame, text="重新修改",
            bg="#7A5A3A", fg="white", font=("Consolas", 9),
            relief=tk.FLAT, padx=8, pady=5, command=on_reedit,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        tk.Button(
            pb_frame, text="完成",
            bg="#3A7A3A", fg="white", font=("Consolas", 9, "bold"),
            relief=tk.FLAT, padx=8, pady=5, command=on_done,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X)

        preview_win.protocol("WM_DELETE_WINDOW", on_reedit)

    def on_confirm() -> None:
        _show_confirm_preview()

    def on_cancel() -> None:
        root.destroy()

    btn_frame = tk.Frame(right_frame, bg="#2B2B2B")
    btn_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

    tk.Button(
        btn_frame, text="確認套用",
        bg="#3A7A3A", fg="white", font=("Consolas", 9, "bold"),
        relief=tk.FLAT, padx=8, pady=5, command=on_confirm,
    ).pack(fill=tk.X, pady=(0, 3))
    tk.Button(
        btn_frame, text="取消",
        bg="#7A3A3A", fg="white", font=("Consolas", 9),
        relief=tk.FLAT, padx=8, pady=5, command=on_cancel,
    ).pack(fill=tk.X)

    # ── Image rendering helpers ───────────────────────────────────────────────
    photo_ref    = [None]
    highlight_id = [None]   # canvas item for the yellow chunk border

    canvas_img_id = canvas.create_image(0, 0, anchor=tk.NW, tags="composite")

    def _refresh_canvas() -> None:
        arr = _render_composite(
            bg_arr, grid_idx, color_palette,
            canvas_w, canvas_h, cols, rows, show_grid_lines,
        )
        img = Image.fromarray(arr, "RGB")
        photo_ref[0] = ImageTk.PhotoImage(img)
        canvas.itemconfig(canvas_img_id, image=photo_ref[0])

    _refresh_canvas()

    # ── Sub-canvas helpers ────────────────────────────────────────────────────
    selected_chunk_pos = [None]  # (chunk_gx, chunk_gz) or None

    def _render_sub_chunk_image(chunk_gx: int, chunk_gz: int) -> np.ndarray:
        """
        Return (SUB_CANVAS_PX, SUB_CANVAS_PX, 3) uint8 for the sub-canvas.
        Crops the terrain background to the chunk region and blends with
        biome colours – identical pipeline to the main canvas.
        """
        # Pixel bounds of this chunk in the main canvas
        px0 = int(chunk_gx * cells_per_chunk * cell_w)
        py0 = int(chunk_gz * cells_per_chunk * cell_h)
        px1 = max(px0 + 1, int((chunk_gx + 1) * cells_per_chunk * cell_w))
        py1 = max(py0 + 1, int((chunk_gz + 1) * cells_per_chunk * cell_h))
        px0, px1 = max(0, px0), min(canvas_w, px1)
        py0, py1 = max(0, py0), min(canvas_h, py1)

        # Crop terrain background and resize to sub-canvas size
        chunk_bg = bg_arr[py0:py1, px0:px1].clip(0, 255).astype(np.uint8)
        chunk_bg_resized = np.asarray(
            Image.fromarray(chunk_bg, "RGB").resize(
                (SUB_CANVAS_PX, SUB_CANVAS_PX), Image.NEAREST
            ),
            dtype=np.float32,
        )

        # Biome colour array for sub-cells (cells_per_chunk × cells_per_chunk)
        sub_colors = np.zeros((cells_per_chunk, cells_per_chunk, 3), dtype=np.float32)
        for sub_gz in range(cells_per_chunk):
            for sub_gx in range(cells_per_chunk):
                gz = chunk_gz * cells_per_chunk + sub_gz
                gx = chunk_gx * cells_per_chunk + sub_gx
                idx = grid_idx[gz, gx] if 0 <= gz < rows and 0 <= gx < cols else fallback_idx
                sub_colors[sub_gz, sub_gx] = color_palette[idx]

        # Scale sub_colors to sub-canvas pixel size (nearest-neighbour)
        y_idx = (np.arange(SUB_CANVAS_PX) * cells_per_chunk / SUB_CANVAS_PX
                 ).astype(np.int32).clip(0, cells_per_chunk - 1)
        x_idx = (np.arange(SUB_CANVAS_PX) * cells_per_chunk / SUB_CANVAS_PX
                 ).astype(np.int32).clip(0, cells_per_chunk - 1)
        scaled_colors = sub_colors[y_idx[:, None], x_idx[None, :]]  # (H, W, 3)

        # 50 % blend
        composite = (chunk_bg_resized * 0.5 + scaled_colors * 0.5).clip(0, 255).astype(np.uint8)

        # Grid lines at cell boundaries
        boost = 55
        for gz in range(1, cells_per_chunk):
            y = int(gz * SUB_CANVAS_PX / cells_per_chunk)
            composite[y] = np.clip(composite[y].astype(np.int32) + boost, 0, 255)
        for gx in range(1, cells_per_chunk):
            x = int(gx * SUB_CANVAS_PX / cells_per_chunk)
            composite[:, x] = np.clip(composite[:, x].astype(np.int32) + boost, 0, 255)

        return composite

    def _draw_sub_canvas(chunk_gx: int, chunk_gz: int) -> None:
        """Render the sub-canvas image for the selected chunk."""
        arr = _render_sub_chunk_image(chunk_gx, chunk_gz)
        img = Image.fromarray(arr, "RGB")
        sub_photo_ref[0] = ImageTk.PhotoImage(img)
        sub_canvas.itemconfig(sub_canvas_img, image=sub_photo_ref[0])

    def _set_highlight(chunk_gx: int, chunk_gz: int) -> None:
        if highlight_id[0] is not None:
            canvas.delete(highlight_id[0])
        x0 = chunk_gx * cells_per_chunk * cell_w
        y0 = chunk_gz * cells_per_chunk * cell_h
        x1 = x0 + cells_per_chunk * cell_w
        y1 = y0 + cells_per_chunk * cell_h
        highlight_id[0] = canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#FFE040", width=2, fill="", tags="highlight",
        )

    def _clear_highlight() -> None:
        if highlight_id[0] is not None:
            canvas.delete(highlight_id[0])
            highlight_id[0] = None

    # ── Detail mode toggle ────────────────────────────────────────────────────
    def on_detail_toggle() -> None:
        if detail_enabled.get():
            sub_frame.pack(fill=tk.X, padx=4, before=btn_frame)
        else:
            sub_frame.pack_forget()
            selected_chunk_pos[0] = None
            _clear_highlight()

    detail_check.config(command=on_detail_toggle)

    # ── Event handlers ────────────────────────────────────────────────────────
    def _update_current_label(biome: str) -> None:
        color = BIOME_COLORS.get(biome, _FALLBACK_COLOR)
        display_color = color if color not in ("#000000", "#111111") else "#AAAAAA"
        current_label.config(
            text="■ " + biome.replace("minecraft:", ""),
            fg=display_color,
        )

    def on_listbox_select(event) -> None:
        sel = listbox.curselection()
        if sel:
            biome = all_biomes[sel[0]]
            selected_biome[0] = biome
            _update_current_label(biome)

    listbox.bind("<<ListboxSelect>>", on_listbox_select)
    default_idx = all_biomes.index("minecraft:plains") if "minecraft:plains" in all_biomes else 0
    listbox.selection_set(default_idx)
    listbox.see(default_idx)

    # Main canvas click/drag
    def _apply_click(x: float, y: float) -> None:
        gx = max(0, min(int(x * cols / canvas_w), cols - 1))
        gz = max(0, min(int(y * rows / canvas_h), rows - 1))

        if detail_enabled.get():
            # Select chunk; open sub-editor
            chunk_gx = gx // cells_per_chunk
            chunk_gz = gz // cells_per_chunk
            if selected_chunk_pos[0] == (chunk_gx, chunk_gz):
                return  # already selected – no redraw needed
            selected_chunk_pos[0] = (chunk_gx, chunk_gz)
            _set_highlight(chunk_gx, chunk_gz)
            sub_info_label.config(
                text=f"區塊 ({chunk_gx}, {chunk_gz})  "
                     f"[{chunk_gx * _CHUNK_BLOCKS}, {chunk_gz * _CHUNK_BLOCKS}]",
                fg="#AAAAAA",
            )
            _draw_sub_canvas(chunk_gx, chunk_gz)
        else:
            # Normal mode: paint entire 16×16-block chunk
            chunk_gx = gx // cells_per_chunk
            chunk_gz = gz // cells_per_chunk
            biome   = selected_biome[0]
            biome_i = biome_to_idx.get(biome, fallback_idx)
            changed = False
            for dz in range(cells_per_chunk):
                for dx in range(cells_per_chunk):
                    cgz = chunk_gz * cells_per_chunk + dz
                    cgx = chunk_gx * cells_per_chunk + dx
                    if 0 <= cgz < rows and 0 <= cgx < cols:
                        if grid[cgz][cgx] != biome:
                            grid[cgz][cgx] = biome
                            grid_idx[cgz, cgx] = biome_i
                            changed = True
            if changed:
                _refresh_canvas()

    canvas.bind("<Button-1>",  lambda e: _apply_click(e.x, e.y))
    canvas.bind("<B1-Motion>", lambda e: _apply_click(e.x, e.y))

    # Sub-canvas click/drag
    def _sub_apply_click(x: float, y: float) -> None:
        if selected_chunk_pos[0] is None:
            return
        chunk_gx, chunk_gz = selected_chunk_pos[0]
        sub_gx = max(0, min(int(x / SUB_CELL_PX), cells_per_chunk - 1))
        sub_gz = max(0, min(int(y / SUB_CELL_PX), cells_per_chunk - 1))
        gz = chunk_gz * cells_per_chunk + sub_gz
        gx = chunk_gx * cells_per_chunk + sub_gx
        biome   = selected_biome[0]
        biome_i = biome_to_idx.get(biome, fallback_idx)
        if 0 <= gz < rows and 0 <= gx < cols and grid[gz][gx] != biome:
            grid[gz][gx] = biome
            grid_idx[gz, gx] = biome_i
            chunk_gx2, chunk_gz2 = selected_chunk_pos[0]
            _draw_sub_canvas(chunk_gx2, chunk_gz2)
            _refresh_canvas()

    sub_canvas.bind("<Button-1>",  lambda e: _sub_apply_click(e.x, e.y))
    sub_canvas.bind("<B1-Motion>", lambda e: _sub_apply_click(e.x, e.y))

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.deiconify()
    root.mainloop()
    return result
