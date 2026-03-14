"""
Per-biome surface layer editor for MCMap.

Shows a single modal window with:
  - Left  : scrollable list of biomes used in the current biome grid
  - Middle : Y-to-block height visualization canvas
  - Right  : editable surface layer table (block, min_y, max_y, blend,
             slope_threshold, steep_block)

Each biome can carry its own surface_layers; biomes without a custom entry
inherit the global surface_layers ("_default") at import time.
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
    selected_biomes:       list[str],
    default_layers:        list[dict],
    biome_surface_layers:  dict,
    min_y:                 int,
    max_y:                 int,
    dirt_top_replacement:  bool = True,
    dirt_top_block:        str  = "minecraft:grass_block",
) -> "dict | None":
    """
    Show the per-biome surface layer editor.

    Parameters
    ----------
    selected_biomes      : unique biome IDs present in the current biome grid
    default_layers       : global surface_layers from config (shown read-only
                           as reference; used as copy-source for new overrides)
    biome_surface_layers : existing per-biome overrides {biome_id: [layers]}
    min_y / max_y        : world Y range (for visualization scaling)

    Returns
    -------
    dict of biome overrides on confirm  (includes "_default" as the editable fallback)
    None on cancel / window close
    """
    # ── Working data ──────────────────────────────────────────────────────
    # data["_default"] = editable fallback (initialised from default_layers)
    # data[biome_id]   = per-biome override (only biomes with custom settings)
    data: dict[str, list[dict]] = {}
    data["_default"] = copy.deepcopy(default_layers or [])
    for biome in selected_biomes:
        if biome in biome_surface_layers:
            data[biome] = copy.deepcopy(biome_surface_layers[biome])
    # Preserve existing overrides for biomes no longer in the grid
    for k, v in biome_surface_layers.items():
        if k not in data:
            data[k] = copy.deepcopy(v)

    result = [None]

    # ── Constants ─────────────────────────────────────────────────────────
    VIZ_W        = 110
    VIZ_H        = 360
    LABEL_W      = 32          # px reserved for Y-axis labels
    BAR_X0       = LABEL_W + 2
    BAR_X1       = VIZ_W - 2
    BIOME_W      = 210         # biome listbox panel width
    COL_WIDTHS   = [22, 5, 5, 5, 10, 18]   # Entry widths in chars
    COL_LABELS   = ["方塊 (block)", "min_y", "max_y", "blend", "坡度閾值", "陡坡方塊"]
    DARK         = "#2B2B2B"
    DARKER       = "#1A1A1A"
    MID          = "#333333"
    FG           = "#DDDDDD"
    FG_DIM       = "#888888"
    FG_HEAD      = "#CCCCCC"
    SEL_BG       = "#4A6A9A"
    ENTRY_FG     = "#DDDDDD"

    # ── Tkinter root ──────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("MCMap – 生態域表面方塊層編輯器")
    root.configure(bg=DARK)
    root.resizable(True, True)
    root.withdraw()

    main_frame = tk.Frame(root, bg=DARK)
    main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # ── Left: biome listbox ───────────────────────────────────────────────
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
                marker = " *" if key in data else ""
                display = "  " + key.replace("minecraft:", "") + marker
            biome_listbox.insert(tk.END, display)
        if cur_sel:
            biome_listbox.selection_set(cur_sel[0])

    _refresh_listbox()

    # ── Right: editor area ────────────────────────────────────────────────
    right_frame = tk.Frame(main_frame, bg=DARK)
    right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    biome_title_var = tk.StringVar(value="[ 預設設定 ]  （唯讀參考）")
    tk.Label(right_frame, textvariable=biome_title_var,
             bg=DARK, fg="#FFCC44",
             font=("Consolas", 10, "bold")).pack(anchor=tk.W, pady=(0, 2))

    hint_var = tk.StringVar(value="點選左側生態域以選擇；點選「複製預設」以建立自訂覆蓋設定。")
    tk.Label(right_frame, textvariable=hint_var,
             bg=DARK, fg=FG_DIM,
             font=("Consolas", 8), wraplength=700, anchor=tk.W,
             justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))

    # ── Dirt-top global settings ───────────────────────────────────────────
    dirt_frame = tk.Frame(right_frame, bg="#222233", bd=1, relief=tk.GROOVE)
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

    editor_frame = tk.Frame(right_frame, bg=DARK)
    editor_frame.pack(fill=tk.BOTH, expand=True)

    # Visualization canvas
    viz_frame = tk.Frame(editor_frame, bg=DARK)
    viz_frame.pack(side=tk.LEFT, padx=(0, 8), anchor=tk.N)

    tk.Label(viz_frame, text="高度視覺化",
             bg=DARK, fg=FG_DIM,
             font=("Consolas", 8)).pack()

    viz_canvas = tk.Canvas(
        viz_frame, width=VIZ_W, height=VIZ_H,
        bg=DARKER, bd=1, relief=tk.SUNKEN, highlightthickness=0,
    )
    viz_canvas.pack()

    # Table frame
    table_frame = tk.Frame(editor_frame, bg=DARK)
    table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # Table header
    hdr = tk.Frame(table_frame, bg=MID)
    hdr.pack(fill=tk.X)
    for lbl, w in zip(COL_LABELS, COL_WIDTHS):
        tk.Label(hdr, text=lbl, bg=MID, fg=FG_HEAD,
                 font=("Consolas", 8, "bold"), width=w, anchor=tk.CENTER,
                 bd=1, relief=tk.GROOVE).pack(side=tk.LEFT)

    # Scrollable rows area
    rows_outer = tk.Frame(table_frame, bg=DARK)
    rows_outer.pack(fill=tk.BOTH, expand=True)

    rows_vsb = tk.Scrollbar(rows_outer, orient=tk.VERTICAL)
    rows_vsb.pack(side=tk.RIGHT, fill=tk.Y)
    rows_cv = tk.Canvas(rows_outer, bg=DARK, highlightthickness=0,
                        yscrollcommand=rows_vsb.set)
    rows_cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    rows_vsb.config(command=rows_cv.yview)

    rows_inner = tk.Frame(rows_cv, bg=DARK)
    rows_cv_window = rows_cv.create_window((0, 0), window=rows_inner, anchor=tk.NW)
    rows_cv.bind(
        "<Configure>",
        lambda e: rows_cv.itemconfig(rows_cv_window, width=e.width),
    )
    rows_inner.bind(
        "<Configure>",
        lambda e: rows_cv.configure(scrollregion=rows_cv.bbox("all")),
    )

    # Tool buttons
    tool_frame = tk.Frame(right_frame, bg=DARK)
    tool_frame.pack(fill=tk.X, pady=(6, 0))

    # Separator + confirm/cancel
    tk.Frame(right_frame, bg="#555555", height=1).pack(fill=tk.X, pady=6)
    btn_frame = tk.Frame(right_frame, bg=DARK)
    btn_frame.pack(fill=tk.X)

    # ── Mutable state ─────────────────────────────────────────────────────
    current_key     = ["_default"]
    selected_row_i  = [-1]
    row_entries:  list[list[tk.Entry]]     = []
    row_vars:     list[list[tk.StringVar]] = []

    # ── Visualization ──────────────────────────────────────────────────────
    def _y_to_px(y: float) -> int:
        frac = (y - min_y) / max(1, max_y - min_y)
        return int(VIZ_H * (1.0 - frac))

    def _draw_viz() -> None:
        viz_canvas.delete("all")
        viz_canvas.create_rectangle(BAR_X0, 0, BAR_X1, VIZ_H,
                                    fill="#222222", outline="#444444")

        layers = _get_view_layers()
        for layer in layers:
            block  = layer.get("block", "minecraft:stone")
            ly_min = layer.get("min_y", min_y)
            ly_max = layer.get("max_y", max_y)
            blend  = layer.get("blend", 0)
            color  = _get_block_color(block)

            py_bot = max(0, min(VIZ_H, _y_to_px(ly_min)))
            py_top = max(0, min(VIZ_H, _y_to_px(ly_max)))

            if py_top < py_bot:
                viz_canvas.create_rectangle(
                    BAR_X0 + 1, py_top, BAR_X1 - 1, py_bot,
                    fill=color, outline="",
                )

            if blend > 0:
                py_lo = max(0, min(VIZ_H, _y_to_px(ly_min - blend)))
                py_hi = max(0, min(VIZ_H, _y_to_px(ly_max + blend)))
                if py_lo > py_bot:
                    viz_canvas.create_rectangle(
                        BAR_X0 + 1, py_bot, BAR_X1 - 1, py_lo,
                        fill=color, outline="", stipple="gray25",
                    )
                if py_hi < py_top:
                    viz_canvas.create_rectangle(
                        BAR_X0 + 1, py_hi, BAR_X1 - 1, py_top,
                        fill=color, outline="", stipple="gray25",
                    )

        for layer in layers:
            py = max(0, min(VIZ_H, _y_to_px(layer.get("max_y", max_y))))
            viz_canvas.create_line(BAR_X0, py, BAR_X1, py, fill="#555555")

        # Y-axis ticks
        span = max_y - min_y
        tick_interval = max(8, (span // 10 // 8) * 8)
        y_start = (min_y // tick_interval) * tick_interval
        for y_val in range(y_start, max_y + tick_interval, tick_interval):
            if min_y <= y_val <= max_y:
                py = _y_to_px(y_val)
                if 0 <= py <= VIZ_H:
                    viz_canvas.create_text(
                        LABEL_W, py, text=str(y_val),
                        fill="#AAAAAA", font=("Consolas", 6), anchor=tk.E,
                    )
                    viz_canvas.create_line(
                        LABEL_W + 1, py, BAR_X0 + 4, py, fill="#555555"
                    )

    # ── Layer helpers ─────────────────────────────────────────────────────
    def _get_view_layers() -> list[dict]:
        """Layers currently displayed (may be _default or a biome override)."""
        key = current_key[0]
        if key in data:
            return data[key]
        return data["_default"]

    def _ensure_own_layers() -> list[dict]:
        """Create a per-biome entry (copy of _default) if it doesn't exist."""
        key = current_key[0]
        if key not in data:
            data[key] = copy.deepcopy(data["_default"])
        _refresh_listbox()
        return data[key]

    def _parse_row_vars() -> list[dict]:
        layers = []
        for rvs in row_vars:
            try:
                block    = rvs[0].get().strip() or "minecraft:stone"
                min_yv   = int(rvs[1].get() or "0")
                max_yv   = int(rvs[2].get() or "0")
                blend_v  = int(rvs[3].get() or "0")
                slope_s  = rvs[4].get().strip()
                steep_s  = rvs[5].get().strip()
            except (ValueError, TypeError):
                block, min_yv, max_yv, blend_v, slope_s, steep_s = \
                    "minecraft:stone", 0, 64, 0, "", ""
            layer: dict = {
                "block": block, "min_y": min_yv,
                "max_y": max_yv, "blend": blend_v,
            }
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
        _draw_viz()

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

    def _add_row_widgets(idx: int, layer: dict, editable: bool) -> None:
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
            _add_row_widgets(i, layer, editable)
        _draw_viz()

    # ── Biome switching ───────────────────────────────────────────────────
    def _switch_biome(key: str) -> None:
        if row_vars:
            _save_rows_to_data()

        current_key[0] = key

        if key == "_default":
            biome_title_var.set(
                "[ 預設設定 ]  ← 可直接編輯，作為所有未自訂生態域的 fallback"
            )
            hint_var.set("直接修改此處即可調整所有未自訂生態域的表面層設定。"
                         "「複製預設」與「移除覆蓋」對此項無效。")
            _build_rows(data["_default"], editable=True)
        else:
            if key in data:
                biome_title_var.set(f"{key.replace('minecraft:', '')}  ★ 已自訂")
                hint_var.set("此生態域已有自訂設定。直接修改表格即可。")
            else:
                biome_title_var.set(
                    f"{key.replace('minecraft:', '')}  （繼承預設 — 點「複製預設」開始自訂）"
                )
                hint_var.set("此生態域目前繼承預設設定。點「複製預設」以建立獨立覆蓋。")
            layers = _get_view_layers()
            _build_rows(copy.deepcopy(layers), editable=True)
        _update_tool_buttons(key)

    def on_listbox_select(event) -> None:
        sel = biome_listbox.curselection()
        if sel:
            key = biome_keys[sel[0]]
            if key != current_key[0]:
                _switch_biome(key)

    biome_listbox.bind("<<ListboxSelect>>", on_listbox_select)
    biome_listbox.selection_set(0)

    # ── Tool buttons ──────────────────────────────────────────────────────
    def on_copy_default() -> None:
        if current_key[0] == "_default":
            return
        layers_copy = copy.deepcopy(data["_default"])
        data[current_key[0]] = layers_copy
        biome_title_var.set(
            f"{current_key[0].replace('minecraft:', '')}  ★ 已自訂"
        )
        hint_var.set("已複製預設設定。直接修改表格即可。")
        _build_rows(layers_copy, editable=True)
        _refresh_listbox()

    def on_add_layer() -> None:
        _save_rows_to_data()
        layers = _ensure_own_layers()
        if layers:
            last = layers[-1]
            new_layer = {
                "block":  last.get("block", "minecraft:stone"),
                "min_y":  last.get("max_y", 64) + 1,
                "max_y":  last.get("max_y", 64) + 32,
                "blend":  last.get("blend", 0),
            }
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
        """Remove custom override for current biome → revert to _default."""
        key = current_key[0]
        if key == "_default" or key not in data:
            return
        del data[key]
        biome_title_var.set(
            f"{key.replace('minecraft:', '')}  （繼承預設）"
        )
        hint_var.set("已移除自訂覆蓋，此生態域將繼承預設設定。")
        _build_rows(copy.deepcopy(data["_default"]), editable=True)
        _refresh_listbox()

    btn_copy_default = tk.Button(tool_frame, text="複製預設", bg="#5A5A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_copy_default)
    btn_copy_default.pack(side=tk.LEFT, padx=(0, 3))
    tk.Button(tool_frame, text=" + 新增層", bg="#3A5A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_add_layer).pack(side=tk.LEFT, padx=(0, 3))
    tk.Button(tool_frame, text=" − 刪除層", bg="#5A3A3A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_del_layer).pack(side=tk.LEFT, padx=(0, 3))
    btn_remove_override = tk.Button(tool_frame, text="移除覆蓋", bg="#5A3A5A", fg="white",
              font=("Consolas", 8), relief=tk.FLAT, padx=6, pady=3,
              command=on_clear_override)
    btn_remove_override.pack(side=tk.LEFT)

    def _update_tool_buttons(key: str) -> None:
        state = tk.DISABLED if key == "_default" else tk.NORMAL
        btn_copy_default.configure(state=state)
        btn_remove_override.configure(state=state)

    # ── Confirm / Cancel ──────────────────────────────────────────────────
    def on_confirm() -> None:
        _save_rows_to_data()
        out: dict = {k: copy.deepcopy(v) for k, v in data.items()}
        out["_dirt_top_replacement"] = dirt_top_var.get()
        out["_dirt_top_block"]       = dirt_block_var.get().strip() or "minecraft:grass_block"
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

    # Centre on screen
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    rw = root.winfo_width()
    rh = root.winfo_height()
    root.geometry(f"+{max(0, (sw - rw) // 2)}+{max(0, (sh - rh) // 2)}")

    root.mainloop()
    return result[0]
