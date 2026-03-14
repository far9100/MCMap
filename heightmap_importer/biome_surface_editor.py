"""
Per-biome surface layer editor for MCMap.

Layout:
  - Far Left   : scrollable list of biomes
  - Left-middle: two stacked viz canvases (surface / subsurface)
  - Right      : two side-by-side editable tables
                  ├─ Surface layers    (per-biome, 6 cols)
                  └─ Subsurface layers (per-biome, 4 cols – all editable)
"""

import copy
import tkinter as tk

# ---------------------------------------------------------------------------
# Block colours for visualization
# ---------------------------------------------------------------------------

BLOCK_COLORS: dict[str, str] = {
    "minecraft:air":             "#111111",
    "minecraft:bedrock":         "#333333",
    "minecraft:stone":           "#888888",
    "minecraft:granite":         "#996655",
    "minecraft:diorite":         "#CCCCCC",
    "minecraft:andesite":        "#999999",
    "minecraft:deepslate":       "#555560",
    "minecraft:calcite":         "#DDDDCC",
    "minecraft:tuff":            "#777766",
    "minecraft:grass_block":     "#5A9E3A",
    "minecraft:dirt":            "#8B5E3C",
    "minecraft:coarse_dirt":     "#7A5030",
    "minecraft:podzol":          "#774422",
    "minecraft:rooted_dirt":     "#6A4020",
    "minecraft:mud":             "#515744",
    "minecraft:gravel":          "#AAAAAA",
    "minecraft:sand":            "#E0CC74",
    "minecraft:red_sand":        "#CC7744",
    "minecraft:sandstone":       "#D4BE64",
    "minecraft:red_sandstone":   "#CC9944",
    "minecraft:snow_block":      "#EEEEFF",
    "minecraft:powder_snow":     "#DDEEFF",
    "minecraft:ice":             "#B0D0E8",
    "minecraft:packed_ice":      "#90C8F0",
    "minecraft:blue_ice":        "#70A8E0",
    "minecraft:clay":            "#9999AA",
    "minecraft:water":           "#3D6FA6",
    "minecraft:mycelium":        "#AA7799",
    "minecraft:moss_block":      "#556B2F",
    "minecraft:terracotta":      "#CC8866",
    "minecraft:obsidian":        "#111122",
    "minecraft:netherrack":      "#802020",
    "minecraft:soul_sand":       "#7A6050",
    "minecraft:magma_block":     "#CC4400",
    "minecraft:basalt":          "#504048",
    "minecraft:blackstone":      "#282428",
    "minecraft:crimson_nylium":  "#892323",
    "minecraft:warped_nylium":   "#167E77",
}

_FALLBACK_BLOCK_COLOR = "#777777"


def _get_block_color(block_id: str) -> str:
    c = BLOCK_COLORS.get(block_id)
    if c:
        return c
    short = block_id.split(":")[-1] if ":" in block_id else block_id
    for k, v in BLOCK_COLORS.items():
        if k.split(":")[-1] == short:
            return v
    return _FALLBACK_BLOCK_COLOR


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_biome_surface_editor(
    selected_biomes:         list[str],
    default_layers:          list[dict],
    biome_surface_layers:    dict,
    min_y:                   int,
    max_y:                   int,
    dirt_top_replacement:    bool = True,
    dirt_top_block:          str  = "minecraft:grass_block",
    subsurface_layers:       "list[dict] | None" = None,
    biome_subsurface_layers: "dict | None" = None,
) -> "dict | None":
    """
    Show the per-biome surface + subsurface layer editor.

    Returns dict on confirm containing:
      - biome surface layer overrides (keyed by biome ID + "_default")
      - "_dirt_top_replacement", "_dirt_top_block"
      - "_biome_subsurface_layers": full per-biome subsurface dict (incl. "_default")
    Returns None on cancel / window close.
    """
    # ── Working data ──────────────────────────────────────────────────────
    # Surface layers: data["_default"] = fallback; data[biome] = override
    data: dict[str, list[dict]] = {}
    data["_default"] = copy.deepcopy(default_layers or [])
    for biome in selected_biomes:
        if biome in biome_surface_layers:
            data[biome] = copy.deepcopy(biome_surface_layers[biome])
    for k, v in biome_surface_layers.items():
        if k not in data:
            data[k] = copy.deepcopy(v)

    # Subsurface layers: sub_data["_default"] = fallback; sub_data[biome] = override
    _bsl = biome_subsurface_layers or {}
    sub_data: dict[str, list[dict]] = {}
    sub_data["_default"] = copy.deepcopy(
        _bsl.get("_default") or subsurface_layers or []
    )
    for biome in selected_biomes:
        if biome in _bsl:
            sub_data[biome] = copy.deepcopy(_bsl[biome])
    for k, v in _bsl.items():
        if k not in sub_data and k != "_default":
            sub_data[k] = copy.deepcopy(v)

    result = [None]

    # ── Constants ─────────────────────────────────────────────────────────
    VIZ_W         = 110
    VIZ_H_SURF    = 220
    VIZ_H_SUB     = 200
    LABEL_W       = 32
    BAR_X0        = LABEL_W + 2
    BAR_X1        = VIZ_W - 2
    BIOME_W       = 180
    COL_WIDTHS    = [22, 5, 5, 5, 10, 18]
    COL_LABELS    = ["方塊 (block)", "min_y", "max_y", "blend", "坡度閾值", "陡坡方塊"]
    SUB_COL_WIDTHS= [22, 5, 5, 5]
    SUB_COL_LABELS= ["方塊 (block)", "min_y", "max_y", "blend"]

    DARK     = "#2B2B2B"
    DARKER   = "#1A1A1A"
    MID      = "#333333"
    FG       = "#DDDDDD"
    FG_DIM   = "#888888"
    FG_HEAD  = "#CCCCCC"
    SEL_BG   = "#4A6A9A"
    ENTRY_FG = "#DDDDDD"

    # ── Tkinter root ──────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("MCMap – 生態域表面方塊層編輯器")
    root.configure(bg=DARK)
    root.resizable(True, True)
    root.withdraw()

    main_frame = tk.Frame(root, bg=DARK)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # ── Far Left: biome listbox ───────────────────────────────────────────
    left_frame = tk.Frame(main_frame, bg=DARK, width=BIOME_W)
    left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    left_frame.pack_propagate(False)

    tk.Label(left_frame, text="─ 生態域列表 ─",
             bg=DARK, fg=FG_HEAD, font=("Consolas", 9, "bold")).pack(pady=(0, 2))
    tk.Label(left_frame, text="* 已自訂  （其餘繼承預設）",
             bg=DARK, fg=FG_DIM, font=("Consolas", 8)).pack(pady=(0, 4))

    lf2 = tk.Frame(left_frame, bg=DARK)
    lf2.pack(fill=tk.BOTH, expand=True)

    lb_vsb = tk.Scrollbar(lf2, orient=tk.VERTICAL)
    lb_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    biome_listbox = tk.Listbox(
        lf2, yscrollcommand=lb_vsb.set,
        bg=DARKER, fg=FG,
        selectbackground=SEL_BG, selectforeground="#FFFFFF",
        font=("Consolas", 9), activestyle="none",
        bd=0, highlightthickness=0,
    )
    biome_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    lb_vsb.config(command=biome_listbox.yview)

    biome_keys = ["_default"] + sorted(selected_biomes)

    def _refresh_listbox() -> None:
        cur_sel = biome_listbox.curselection()
        biome_listbox.delete(0, tk.END)
        for key in biome_keys:
            if key == "_default":
                display = "  [ 預設設定 ]"
            else:
                surf_mark = "s" if key in data    else "·"
                sub_mark  = "u" if key in sub_data else "·"
                display = f"  [{surf_mark}{sub_mark}] " + key.replace("minecraft:", "")
            biome_listbox.insert(tk.END, display)
        if cur_sel:
            biome_listbox.selection_set(cur_sel[0])

    _refresh_listbox()

    # ── Content area ─────────────────────────────────────────────────────
    content_frame = tk.Frame(main_frame, bg=DARK)
    content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    biome_title_var = tk.StringVar(value="[ 預設設定 ]")
    tk.Label(content_frame, textvariable=biome_title_var,
             bg=DARK, fg="#FFCC44",
             font=("Consolas", 10, "bold")).pack(anchor=tk.W, pady=(0, 2))

    hint_var = tk.StringVar(value="點選左側生態域以選擇。")
    tk.Label(content_frame, textvariable=hint_var,
             bg=DARK, fg=FG_DIM,
             font=("Consolas", 8), wraplength=900, anchor=tk.W,
             justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 4))

    # Dirt Top (full width)
    dirt_frame = tk.Frame(content_frame, bg="#222233", bd=1, relief=tk.GROOVE)
    dirt_frame.pack(fill=tk.X, pady=(0, 6))
    tk.Label(dirt_frame, text="Dirt Top 設定",
             bg="#222233", fg="#AABBDD", font=("Consolas", 8, "bold")).pack(
                 side=tk.LEFT, padx=(6, 8))
    dirt_top_var = tk.BooleanVar(value=dirt_top_replacement)
    tk.Checkbutton(
        dirt_frame, text="啟用 dirt_top_replacement",
        variable=dirt_top_var,
        bg="#222233", fg="#CCDDEE",
        selectcolor="#1A1A2A", activebackground="#222233",
        font=("Consolas", 8),
    ).pack(side=tk.LEFT, padx=(0, 8))
    tk.Label(dirt_frame, text="替換方塊：",
             bg="#222233", fg="#CCDDEE", font=("Consolas", 8)).pack(side=tk.LEFT)
    dirt_block_var = tk.StringVar(value=dirt_top_block)
    tk.Entry(
        dirt_frame, textvariable=dirt_block_var, width=24,
        bg="#1A1A2A", fg="#DDDDFF", insertbackground="#DDDDFF",
        bd=1, relief=tk.SUNKEN, font=("Consolas", 8),
    ).pack(side=tk.LEFT, padx=(0, 6), pady=3)

    # ── Body: viz column + tables area ───────────────────────────────────
    body_frame = tk.Frame(content_frame, bg=DARK)
    body_frame.pack(fill=tk.BOTH, expand=True)

    # ── Viz column ────────────────────────────────────────────────────────
    viz_column = tk.Frame(body_frame, bg=DARK)
    viz_column.pack(side=tk.LEFT, padx=(0, 8), anchor=tk.N)

    def _y_to_px(y: float, viz_h: int) -> int:
        frac = (y - min_y) / max(1, max_y - min_y)
        return int(viz_h * (1.0 - frac))

    def _draw_canvas(canvas: tk.Canvas, viz_h: int, layers: list[dict]) -> None:
        canvas.delete("all")
        canvas.create_rectangle(BAR_X0, 0, BAR_X1, viz_h,
                                 fill="#222222", outline="#444444")
        for layer in layers:
            block  = layer.get("block", "minecraft:stone")
            ly_min = layer.get("min_y", min_y)
            ly_max = layer.get("max_y", max_y)
            blend  = layer.get("blend", 0)
            color  = _get_block_color(block)
            py_bot = max(0, min(viz_h, _y_to_px(ly_min, viz_h)))
            py_top = max(0, min(viz_h, _y_to_px(ly_max, viz_h)))
            if py_top < py_bot:
                canvas.create_rectangle(
                    BAR_X0 + 1, py_top, BAR_X1 - 1, py_bot, fill=color, outline="")
            if blend > 0:
                py_lo = max(0, min(viz_h, _y_to_px(ly_min - blend, viz_h)))
                py_hi = max(0, min(viz_h, _y_to_px(ly_max + blend, viz_h)))
                if py_lo > py_bot:
                    canvas.create_rectangle(
                        BAR_X0 + 1, py_bot, BAR_X1 - 1, py_lo,
                        fill=color, outline="", stipple="gray25")
                if py_hi < py_top:
                    canvas.create_rectangle(
                        BAR_X0 + 1, py_hi, BAR_X1 - 1, py_top,
                        fill=color, outline="", stipple="gray25")
        for layer in layers:
            py = max(0, min(viz_h, _y_to_px(layer.get("max_y", max_y), viz_h)))
            canvas.create_line(BAR_X0, py, BAR_X1, py, fill="#555555")
        span = max_y - min_y
        tick_interval = max(8, (span // 10 // 8) * 8)
        y_start = (min_y // tick_interval) * tick_interval
        for y_val in range(y_start, max_y + tick_interval, tick_interval):
            if min_y <= y_val <= max_y:
                py = _y_to_px(y_val, viz_h)
                if 0 <= py <= viz_h:
                    canvas.create_text(LABEL_W, py, text=str(y_val),
                                       fill="#AAAAAA", font=("Consolas", 6), anchor=tk.E)
                    canvas.create_line(LABEL_W + 1, py, BAR_X0 + 4, py, fill="#555555")

    tk.Label(viz_column, text="表面方塊示意",
             bg=DARK, fg=FG_DIM, font=("Consolas", 8)).pack()
    surf_canvas = tk.Canvas(viz_column, width=VIZ_W, height=VIZ_H_SURF,
                            bg=DARKER, bd=1, relief=tk.SUNKEN, highlightthickness=0)
    surf_canvas.pack()
    tk.Frame(viz_column, bg=DARK, height=8).pack()
    tk.Label(viz_column, text="地下岩層示意",
             bg=DARK, fg="#DDAAFF", font=("Consolas", 8)).pack()
    sub_canvas = tk.Canvas(viz_column, width=VIZ_W, height=VIZ_H_SUB,
                           bg=DARKER, bd=1, relief=tk.SUNKEN, highlightthickness=0)
    sub_canvas.pack()

    # ── Tables area ───────────────────────────────────────────────────────
    tables_area = tk.Frame(body_frame, bg=DARK)
    tables_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # ── Surface table (left) ──────────────────────────────────────────────
    surf_section = tk.Frame(tables_area, bg=DARK)
    surf_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

    tk.Label(surf_section, text="表面方塊層",
             bg=DARK, fg=FG_HEAD, font=("Consolas", 8, "bold")).pack(anchor=tk.W, pady=(0, 2))
    surf_hdr = tk.Frame(surf_section, bg=MID)
    surf_hdr.pack(fill=tk.X)
    for lbl, w in zip(COL_LABELS, COL_WIDTHS):
        tk.Label(surf_hdr, text=lbl, bg=MID, fg=FG_HEAD,
                 font=("Consolas", 8, "bold"), width=w, anchor=tk.CENTER,
                 bd=1, relief=tk.GROOVE).pack(side=tk.LEFT)

    surf_rows_outer = tk.Frame(surf_section, bg=DARK)
    surf_rows_outer.pack(fill=tk.BOTH, expand=True)
    surf_vsb = tk.Scrollbar(surf_rows_outer, orient=tk.VERTICAL)
    surf_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    surf_cv = tk.Canvas(surf_rows_outer, bg=DARK, highlightthickness=0,
                        yscrollcommand=surf_vsb.set)
    surf_cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    surf_vsb.config(command=surf_cv.yview)
    rows_inner = tk.Frame(surf_cv, bg=DARK)
    rows_cv_win = surf_cv.create_window((0, 0), window=rows_inner, anchor=tk.NW)
    surf_cv.bind("<Configure>",
                 lambda e: surf_cv.itemconfig(rows_cv_win, width=e.width))
    rows_inner.bind("<Configure>",
                    lambda e: surf_cv.configure(scrollregion=surf_cv.bbox("all")))

    surf_tool = tk.Frame(surf_section, bg=DARK)
    surf_tool.pack(fill=tk.X, pady=(4, 0))

    # ── Subsurface table (right) ──────────────────────────────────────────
    sub_section = tk.Frame(tables_area, bg="#1C1822", bd=1, relief=tk.GROOVE)
    sub_section.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    tk.Label(sub_section, text="地下岩層",
             bg="#1C1822", fg="#DDAAFF", font=("Consolas", 8, "bold")).pack(
                 anchor=tk.W, padx=6, pady=(4, 0))
    tk.Label(sub_section, text="表面層之下、岩床之上  空=全石頭",
             bg="#1C1822", fg="#888888", font=("Consolas", 7)).pack(anchor=tk.W, padx=6)
    sub_hdr = tk.Frame(sub_section, bg=MID)
    sub_hdr.pack(fill=tk.X, padx=6, pady=(2, 0))
    for lbl, w in zip(SUB_COL_LABELS, SUB_COL_WIDTHS):
        tk.Label(sub_hdr, text=lbl, bg=MID, fg=FG_HEAD,
                 font=("Consolas", 8, "bold"), width=w, anchor=tk.CENTER,
                 bd=1, relief=tk.GROOVE).pack(side=tk.LEFT)

    sub_rows_outer = tk.Frame(sub_section, bg=DARK)
    sub_rows_outer.pack(fill=tk.BOTH, expand=True, padx=6)
    sub_vsb = tk.Scrollbar(sub_rows_outer, orient=tk.VERTICAL)
    sub_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    sub_cv = tk.Canvas(sub_rows_outer, bg=DARK, highlightthickness=0,
                       yscrollcommand=sub_vsb.set)
    sub_cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sub_vsb.config(command=sub_cv.yview)
    sub_rows_inner = tk.Frame(sub_cv, bg=DARK)
    sub_rows_cv_win = sub_cv.create_window((0, 0), window=sub_rows_inner, anchor=tk.NW)
    sub_cv.bind("<Configure>",
                lambda e: sub_cv.itemconfig(sub_rows_cv_win, width=e.width))
    sub_rows_inner.bind("<Configure>",
                        lambda e: sub_cv.configure(scrollregion=sub_cv.bbox("all")))

    sub_tool = tk.Frame(sub_section, bg="#1C1822")
    sub_tool.pack(fill=tk.X, padx=6, pady=(4, 4))

    # ── Mutable row state ─────────────────────────────────────────────────
    current_key    = ["_default"]
    selected_row_i = [-1]
    row_entries:  list[list[tk.Entry]]     = []
    row_vars:     list[list[tk.StringVar]] = []

    sub_selected_row = [-1]
    sub_row_vars:    list[list[tk.StringVar]] = []
    sub_row_entries: list[list[tk.Entry]]     = []

    # ── Surface layer helpers ──────────────────────────────────────────────
    def _get_view_layers() -> list[dict]:
        key = current_key[0]
        return data[key] if key in data else data["_default"]

    def _ensure_own_layers() -> list[dict]:
        key = current_key[0]
        if key not in data:
            data[key] = copy.deepcopy(data["_default"])
        _refresh_listbox()
        return data[key]

    def _parse_row_vars() -> list[dict]:
        layers = []
        for rvs in row_vars:
            try:
                block   = rvs[0].get().strip() or "minecraft:stone"
                min_yv  = int(rvs[1].get() or "0")
                max_yv  = int(rvs[2].get() or "0")
                blend_v = int(rvs[3].get() or "0")
                slope_s = rvs[4].get().strip()
                steep_s = rvs[5].get().strip()
            except (ValueError, TypeError):
                block, min_yv, max_yv, blend_v, slope_s, steep_s = \
                    "minecraft:stone", 0, 64, 0, "", ""
            layer: dict = {"block": block, "min_y": min_yv, "max_y": max_yv, "blend": blend_v}
            if slope_s:
                try:
                    layer["slope_threshold"] = float(slope_s)
                except ValueError:
                    pass
            if steep_s:
                layer["steep_block"] = steep_s
            layers.append(layer)
        return layers

    def _save_rows_to_data() -> None:
        if row_vars:
            data[current_key[0]] = _parse_row_vars()

    def _on_entry_change(*_args) -> None:
        _save_rows_to_data()
        _draw_surf_viz()

    def _clear_rows() -> None:
        for child in rows_inner.winfo_children():
            child.destroy()
        row_entries.clear()
        row_vars.clear()
        selected_row_i[0] = -1

    def _select_row(idx: int) -> None:
        selected_row_i[0] = idx
        for i, es in enumerate(row_entries):
            bg = SEL_BG if i == idx else DARKER
            for e in es:
                e.configure(bg=bg)

    def _add_row_widget(idx: int, layer: dict, editable: bool) -> None:
        rf = tk.Frame(rows_inner, bg=DARK)
        rf.pack(fill=tk.X)
        vals = [
            layer.get("block", "minecraft:stone"),
            str(layer.get("min_y", 0)),
            str(layer.get("max_y", 64)),
            str(layer.get("blend", 0)),
            str(layer.get("slope_threshold", "")) if "slope_threshold" in layer else "",
            layer.get("steep_block", ""),
        ]
        evs: list[tk.StringVar] = []
        es:  list[tk.Entry]     = []
        for val, w in zip(vals, COL_WIDTHS):
            sv = tk.StringVar(value=val)
            if editable:
                sv.trace_add("write", _on_entry_change)
            e = tk.Entry(
                rf, textvariable=sv, width=w,
                bg=DARKER, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                bd=1, relief=tk.SUNKEN, font=("Consolas", 8),
                state="normal" if editable else "disabled",
                disabledforeground=FG_DIM, disabledbackground="#222222",
            )
            e.pack(side=tk.LEFT)
            if editable:
                e.bind("<Button-1>", lambda event, i=idx: _select_row(i))
            evs.append(sv)
            es.append(e)
        row_vars.append(evs)
        row_entries.append(es)

    def _build_rows(layers: list[dict], editable: bool) -> None:
        _clear_rows()
        for i, layer in enumerate(layers):
            _add_row_widget(i, layer, editable)
        _draw_surf_viz()

    # ── Subsurface layer helpers ───────────────────────────────────────────
    def _get_sub_view_layers() -> list[dict]:
        key = current_key[0]
        return sub_data[key] if key in sub_data else sub_data["_default"]

    def _ensure_own_sub_layers() -> list[dict]:
        key = current_key[0]
        if key not in sub_data:
            sub_data[key] = copy.deepcopy(sub_data["_default"])
        _refresh_listbox()
        return sub_data[key]

    def _parse_sub_row_vars() -> list[dict]:
        out_layers = []
        for rvs in sub_row_vars:
            try:
                block   = rvs[0].get().strip() or "minecraft:stone"
                min_yv  = int(rvs[1].get() or "0")
                max_yv  = int(rvs[2].get() or "0")
                blend_v = int(rvs[3].get() or "0")
            except (ValueError, TypeError):
                block, min_yv, max_yv, blend_v = "minecraft:stone", 0, 0, 0
            out_layers.append({"block": block, "min_y": min_yv,
                                "max_y": max_yv, "blend": blend_v})
        return out_layers

    def _save_sub_rows_to_data() -> None:
        if sub_row_vars:
            sub_data[current_key[0]] = _parse_sub_row_vars()

    def _sub_on_change(*_args) -> None:
        _save_sub_rows_to_data()
        _draw_sub_viz()

    def _sub_clear_rows() -> None:
        for child in sub_rows_inner.winfo_children():
            child.destroy()
        sub_row_vars.clear()
        sub_row_entries.clear()
        sub_selected_row[0] = -1

    def _sub_select_row(idx: int) -> None:
        sub_selected_row[0] = idx
        for i, es in enumerate(sub_row_entries):
            bg = SEL_BG if i == idx else DARKER
            for e in es:
                e.configure(bg=bg)

    def _sub_add_row_widget(idx: int, layer: dict) -> None:
        rf = tk.Frame(sub_rows_inner, bg=DARK)
        rf.pack(fill=tk.X)
        vals = [
            layer.get("block", "minecraft:stone"),
            str(layer.get("min_y", 0)),
            str(layer.get("max_y", 0)),
            str(layer.get("blend", 0)),
        ]
        evs: list[tk.StringVar] = []
        es:  list[tk.Entry]     = []
        for val, w in zip(vals, SUB_COL_WIDTHS):
            sv = tk.StringVar(value=val)
            sv.trace_add("write", _sub_on_change)
            e = tk.Entry(
                rf, textvariable=sv, width=w,
                bg=DARKER, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                bd=1, relief=tk.SUNKEN, font=("Consolas", 8),
            )
            e.pack(side=tk.LEFT)
            e.bind("<Button-1>", lambda event, i=idx: _sub_select_row(i))
            evs.append(sv)
            es.append(e)
        sub_row_vars.append(evs)
        sub_row_entries.append(es)

    def _build_sub_rows(layers: list[dict]) -> None:
        _sub_clear_rows()
        for i, layer in enumerate(layers):
            _sub_add_row_widget(i, layer)
        _draw_sub_viz()

    # ── Viz draw helpers ──────────────────────────────────────────────────
    def _draw_surf_viz() -> None:
        _draw_canvas(surf_canvas, VIZ_H_SURF, _get_view_layers())

    def _draw_sub_viz() -> None:
        _draw_canvas(sub_canvas, VIZ_H_SUB, _get_sub_view_layers())

    # ── Biome switching ───────────────────────────────────────────────────
    def _switch_biome(key: str) -> None:
        if row_vars:
            _save_rows_to_data()
        if sub_row_vars:
            _save_sub_rows_to_data()
        current_key[0] = key

        if key == "_default":
            biome_title_var.set("[ 預設設定 ]  ← 可直接編輯，作為所有未自訂生態域的 fallback")
            hint_var.set("直接修改此處即可調整所有未自訂生態域的設定。「複製預設」與「移除覆蓋」對此項無效。")
            _build_rows(data["_default"], editable=True)
        else:
            surf_mark = "★ 已自訂表面" if key in data    else "（繼承預設）"
            sub_mark  = "★ 已自訂地下" if key in sub_data else "（繼承預設）"
            biome_title_var.set(f"{key.replace('minecraft:', '')}  表面:{surf_mark}  地下:{sub_mark}")
            hint_var.set("點「複製預設」為該生態域建立獨立覆蓋；點「移除覆蓋」恢復繼承預設。")
            _build_rows(copy.deepcopy(_get_view_layers()), editable=True)

        _build_sub_rows(copy.deepcopy(_get_sub_view_layers()))
        _update_tool_buttons(key)

    def on_listbox_select(event) -> None:
        sel = biome_listbox.curselection()
        if sel:
            key = biome_keys[sel[0]]
            if key != current_key[0]:
                _switch_biome(key)

    biome_listbox.bind("<<ListboxSelect>>", on_listbox_select)
    biome_listbox.selection_set(0)

    # ── Surface tool button actions ───────────────────────────────────────
    def on_copy_default() -> None:
        if current_key[0] == "_default":
            return
        lc = copy.deepcopy(data["_default"])
        data[current_key[0]] = lc
        _build_rows(lc, editable=True)
        _refresh_listbox()
        _update_tool_buttons(current_key[0])

    def on_add_layer() -> None:
        _save_rows_to_data()
        layers = _ensure_own_layers()
        if layers:
            last = layers[-1]
            new_layer = {"block": last.get("block", "minecraft:stone"),
                         "min_y": last.get("max_y", 64) + 1,
                         "max_y": last.get("max_y", 64) + 32,
                         "blend": last.get("blend", 0)}
        else:
            new_layer = {"block": "minecraft:stone", "min_y": 0, "max_y": 64, "blend": 0}
        layers.append(new_layer)
        data[current_key[0]] = layers
        _build_rows(layers, editable=True)

    def on_del_layer() -> None:
        idx = selected_row_i[0]
        _save_rows_to_data()
        layers = _ensure_own_layers()
        if 0 <= idx < len(layers):
            layers.pop(idx)
            data[current_key[0]] = layers
            _build_rows(layers, editable=True)
            selected_row_i[0] = -1

    def on_clear_override() -> None:
        key = current_key[0]
        if key == "_default" or key not in data:
            return
        del data[key]
        _build_rows(copy.deepcopy(data["_default"]), editable=True)
        _refresh_listbox()
        _update_tool_buttons(key)

    # ── Subsurface tool button actions ────────────────────────────────────
    def on_sub_copy_default() -> None:
        if current_key[0] == "_default":
            return
        lc = copy.deepcopy(sub_data["_default"])
        sub_data[current_key[0]] = lc
        _build_sub_rows(lc)
        _refresh_listbox()
        _update_tool_buttons(current_key[0])

    def on_sub_add_layer() -> None:
        _save_sub_rows_to_data()
        layers = _ensure_own_sub_layers()
        if layers:
            last = layers[-1]
            new_layer = {"block": last.get("block", "minecraft:stone"),
                         "min_y": last.get("max_y", 0) + 1,
                         "max_y": last.get("max_y", 0) + 16,
                         "blend": last.get("blend", 0)}
        else:
            new_layer = {"block": "minecraft:deepslate", "min_y": -63, "max_y": -1, "blend": 4}
        layers.append(new_layer)
        sub_data[current_key[0]] = layers
        _build_sub_rows(layers)

    def on_sub_del_layer() -> None:
        idx = sub_selected_row[0]
        _save_sub_rows_to_data()
        layers = _ensure_own_sub_layers()
        if 0 <= idx < len(layers):
            layers.pop(idx)
            sub_data[current_key[0]] = layers
            _build_sub_rows(layers)
            sub_selected_row[0] = -1

    def on_sub_clear_override() -> None:
        key = current_key[0]
        if key == "_default" or key not in sub_data:
            return
        del sub_data[key]
        _build_sub_rows(copy.deepcopy(sub_data["_default"]))
        _refresh_listbox()
        _update_tool_buttons(key)

    # ── Build tool buttons (after all action functions defined) ───────────
    btn_copy_default = tk.Button(surf_tool, text="複製預設", bg="#5A5A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_copy_default)
    btn_copy_default.pack(side=tk.LEFT, padx=(0, 3))
    tk.Button(surf_tool, text=" + 新增層", bg="#3A5A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_add_layer).pack(side=tk.LEFT, padx=(0, 3))
    tk.Button(surf_tool, text=" − 刪除層", bg="#5A3A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_del_layer).pack(side=tk.LEFT, padx=(0, 3))
    btn_remove_override = tk.Button(surf_tool, text="移除覆蓋", bg="#5A3A5A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_clear_override)
    btn_remove_override.pack(side=tk.LEFT)

    btn_sub_copy_default = tk.Button(sub_tool, text="複製預設", bg="#5A5A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=2,
              command=on_sub_copy_default)
    btn_sub_copy_default.pack(side=tk.LEFT, padx=(0, 3))
    tk.Button(sub_tool, text=" + 新增層", bg="#3A5A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=2,
              command=on_sub_add_layer).pack(side=tk.LEFT, padx=(0, 3))
    tk.Button(sub_tool, text=" − 刪除層", bg="#5A3A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=2,
              command=on_sub_del_layer).pack(side=tk.LEFT, padx=(0, 3))
    btn_sub_remove_override = tk.Button(sub_tool, text="移除覆蓋", bg="#5A3A5A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=2,
              command=on_sub_clear_override)
    btn_sub_remove_override.pack(side=tk.LEFT)

    def _update_tool_buttons(key: str) -> None:
        state = tk.DISABLED if key == "_default" else tk.NORMAL
        btn_copy_default.configure(state=state)
        btn_remove_override.configure(state=state)
        btn_sub_copy_default.configure(state=state)
        btn_sub_remove_override.configure(state=state)

    # ── Confirm / Cancel ──────────────────────────────────────────────────
    tk.Frame(content_frame, bg="#555555", height=1).pack(fill=tk.X, pady=6)
    btn_frame = tk.Frame(content_frame, bg=DARK)
    btn_frame.pack(fill=tk.X)

    def on_confirm() -> None:
        _save_rows_to_data()
        _save_sub_rows_to_data()
        out: dict = {k: copy.deepcopy(v) for k, v in data.items()}
        out["_dirt_top_replacement"]    = dirt_top_var.get()
        out["_dirt_top_block"]          = dirt_block_var.get().strip() or "minecraft:grass_block"
        out["_biome_subsurface_layers"] = {k: copy.deepcopy(v) for k, v in sub_data.items()}
        result[0] = out
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    tk.Button(btn_frame, text="完成套用", bg="#3A7A3A", fg="white",
              font=("Consolas", 9, "bold"), relief=tk.FLAT, padx=10, pady=5,
              command=on_confirm).pack(side=tk.RIGHT, padx=(4, 0))
    tk.Button(btn_frame, text="取消", bg="#7A3A3A", fg="white",
              font=("Consolas", 9), relief=tk.FLAT, padx=10, pady=5,
              command=on_cancel).pack(side=tk.RIGHT)
    tk.Label(btn_frame,
             text="「完成套用」將在本次匯入中使用以上設定（不會寫回 config.json）",
             bg=DARK, fg=FG_DIM, font=("Consolas", 8)).pack(side=tk.LEFT)

    # ── Initial state ─────────────────────────────────────────────────────
    _switch_biome("_default")
    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.deiconify()

    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    rw = root.winfo_width()
    rh = root.winfo_height()
    root.geometry(f"+{max(0, (sw - rw) // 2)}+{max(0, (sh - rh) // 2)}")

    root.mainloop()
    return result[0]
