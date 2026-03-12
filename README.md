# MCMap — HeightMap → Minecraft World Importer

將灰階 HeightMap 圖片的地形直接寫入 **Minecraft Java Edition 1.21.1** 存檔。

---

## 資料夾結構

```
MCMap/
├── input/
│   ├── heightmaps/    ← HeightMap 圖片放這裡（PNG / JPG / BMP / TIFF / WebP）
│   └── saves/         ← MC 存檔資料夾放這裡（需含 region/ 子資料夾）
├── output/            ← 修改後存檔自動輸出至此（每次執行會完整覆蓋）
├── config.json        ← 高度、海平面、雪線、region 範圍設定
├── main.py
├── requirements.txt
└── heightmap_importer/
    ├── blocks.py      ← 方塊分層邏輯
    ├── chunk.py       ← Chunk NBT 編輯（numpy 向量化）
    ├── heightmap.py   ← 圖片載入與高度查詢
    ├── importer.py    ← 主要匯入流程
    ├── preview.py     ← 3D + 俯視預覽渲染
    └── region.py      ← Anvil .mca 讀寫
```

> **原始存檔不會被修改**。程式先將 `input/world/` 複製到 `output/`，再修改副本。

---

## 安裝

```bash
pip install -r requirements.txt
```

依賴套件：`Pillow`、`nbtlib`、`numpy`、`matplotlib`、`tqdm`

---

## 快速開始

1. 把 HeightMap 圖片放進 `input/heightmaps/`
2. 把 MC 存檔**內容**直接放進 `input/saves/`
   - 正確：`input/saves/region/`、`input/saves/level.dat`、…
   - 錯誤：`input/saves/MyWorld/region/`（多包一層資料夾）
3. 調整 `config.json`（可選）
4. 執行：

```bash
python main.py --world input/saves/<存檔名稱>
```

若存檔內容已直接放在 `input/saves/`（不含子資料夾），可省略 `--world`：

```bash
python main.py
```

程式會自動：
- 依 `config.json` 中的 `region_origin` 與 `region_size` 決定座標
- 依圖片尺寸自動計算縮放比例
- 渲染 3D + 俯視預覽圖（`output/preview.png`）並開啟
- 詢問確認後寫入存檔
- 完成後顯示渲染與套用的耗時

---

## config.json

```json
{
  "min_y": -63,
  "max_y": 319,
  "sea_level": 0,
  "snow_line": 256,
  "region_origin": [0, 0],
  "region_size": [2, 2]
}
```

| 欄位 | 說明 |
|------|------|
| `min_y` | 像素值 0（黑）對應的 MC Y 高度 |
| `max_y` | 像素值 255（白）對應的 MC Y 高度 |
| `sea_level` | 海平面 Y，決定草地 / 沙地分界，以及顏色映射 |
| `snow_line` | 雪線 Y，此高度以上的地表替換為 `snow_block` |
| `region_origin` | 面朝北時左上角（西北角）的 region 座標 `[rx, rz]`，預設 `[0, 0]` = `r.0.0.mca` |
| `region_size` | 地形範圍，單位為 region（每 region = 512 格），預設 `[2, 2]` = 1024×1024 格 |

`--x` / `--z` 省略時由 `region_origin × 512` 自動推算；
`--scale` 省略時由 `region_size` 與圖片尺寸自動計算。

---

## 工作流程

```
HeightMap 圖片
      │
      ▼
 [1] 渲染預覽圖 ── output/preview.png（自動開啟）
      │
      ▼  詢問確認 [y/N]
      │
 [2] 複製存檔 input/world/ → output/
      │
      ▼
 [3] 依 region_origin / region_size 修改 output/ 中的 .mca 檔案
      │
      ▼
 完成！顯示渲染耗時 + 套用耗時
      │
      ▼
 在 Minecraft 1.21.1 中開啟 output/ 存檔
```

---

## 指令參數

```bash
python main.py [options]
```

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--world` / `-w` | `input/saves` | 輸入 MC 存檔資料夾 |
| `--heightmap` / `-i` | *(自動搜尋)* | HeightMap 圖片路徑 |
| `--output` / `-o` | `output` | 輸出資料夾 |
| `--x` | *(由 region_origin 推算)* | 圖片左上角的 MC X 座標 |
| `--z` | *(由 region_origin 推算)* | 圖片左上角的 MC Z 座標 |
| `--region-origin RX RZ` | *(由 config.json)* | 覆蓋 region 起始座標 |
| `--region-size W H` | *(由 config.json)* | 覆蓋 region 範圍（單位：region） |
| `--min-y` | *(由 config.json)* | 像素值 0 → 此 Y 高度 |
| `--max-y` | *(由 config.json)* | 像素值 255 → 此 Y 高度 |
| `--sea-level` | *(由 config.json)* | 海平面 Y |
| `--snow-line` | *(由 config.json)* | 雪線 Y |
| `--scale` | *(自動計算)* | 每像素對應幾個 MC 方塊（整數 ≥ 1） |
| `--preview-only` | — | 只渲染預覽圖，不套用至存檔（不需要 world 資料夾） |
| `--no-preview` | — | 跳過預覽，直接套用（與 `--preview-only` 互斥） |
| `--no-open` | — | 渲染後不自動開啟預覽圖 |
| `--yes` / `-y` | — | 預覽後自動確認，不詢問 |
| `--quiet` / `-q` | — | 不顯示進度訊息 |

---

## 使用範例

```bash
# 最簡用法：存檔內容直接放在 input/world/，依 config.json 自動推算所有參數
python main.py

# 存檔在子資料夾（最常見情況）
python main.py --world input/saves/TEST

# 只渲染預覽（不需要 MC 存檔）
python main.py --preview-only

# 跳過預覽、自動確認，適合批次處理
python main.py --world input/saves/TEST --no-preview --yes

# 指定起始座標與縮放
python main.py --x -512 --z -512 --scale 2

# 指定 region 範圍（西北角 r.-1.-1，覆蓋 2×2 regions）
python main.py --region-origin -1 -1 --region-size 2 2

# 完整指定所有路徑與參數
python main.py --world "C:/saves/MyWorld" \
               --heightmap "C:/maps/terrain.png" \
               --output "C:/saves/MyWorld_modified" \
               --x -512 --z -512 --scale 4 \
               --min-y -60 --max-y 200 --yes
```

---

## 執行輸出範例

```
================================================================
  MCMap – HeightMap → Minecraft 1.21.1 World Importer
================================================================
  輸入存檔  : input/saves/TEST
  HeightMap : input\heightmaps\small_island.jpg
  輸出資料夾: output
  Region 起點: r.0.0  大小: 2×2 regions (1024×1024 格)
  起始座標  : X=0, Z=0
  Y 範圍    : -63 ~ 319
  海平面    : Y=0
  雪線      : Y=256
  縮放比例  : 2 格/像素
----------------------------------------------------------------

[1/2] 渲染地形預覽...
  預覽圖已儲存：...\output\preview.png

[2/2] 套用地形至 MC 存檔...
Copying world to output folder: output ...
Copy complete.
  Chunks: 3969/3969 [██████████████████████████████] 100.0%  elapsed 00:02  ETA 00:00
Saving 4 region file(s)...
Done. Output world: output

完成！請在 Minecraft 1.21.1 中開啟 'output' 資料夾中的存檔。

────────────────────────────
  渲染預覽：   3.2 秒
  套用地形：   2.1 秒
  總計    ：   5.3 秒
────────────────────────────
```

---

## HeightMap 規格

| 項目 | 說明 |
|------|------|
| 支援格式 | PNG / JPG / BMP / TIFF / WebP |
| 色彩模式 | 灰階（程式自動轉換） |
| 像素值 0（黑）| 對應 `min_y` |
| 像素值 255（白）| 對應 `max_y` |
| 映射方式 | 線性插值 |
| 16 位元 PNG | 支援（自動正規化） |

---

## 方塊分層邏輯

| 位置 | 方塊 |
|------|------|
| Y = -64（世界底部）| `bedrock` |
| 地表（高於海平面，低於雪線）| `grass_block` |
| 地表（高於海平面，高於雪線）| `snow_block` |
| 地表下 1–3 層（高於海平面）| `dirt` |
| 地表（海平面及以下）| `sand` |
| 地表下 1–3 層（海平面及以下）| `sand` |
| 更深層 | `stone` |
| 地表以上 | `air` |

---

## 技術細節

### Anvil 格式（1.21.1）

| 項目 | 說明 |
|------|------|
| DataVersion | 3955（1.21.1） |
| 世界高度 | Y = -64 到 319（共 384 格） |
| Section Y 範圍 | -4 到 19（共 24 個 section） |
| Chunk 結構 | 無 `Level` wrapper，資料直接在根層 |
| Block 資料鍵 | `sections[n]["block_states"]["palette/data"]` |
| BlockStates 打包 | `bits = max(4, ⌈log₂(palette_size)⌉)`，no-spanning |
| Heightmap 打包 | 9 bits/entry，stored = Y + 65，7 values/long |

### 效能

| 指標 | 數值 |
|------|------|
| 處理速度 | ~1500–2000 chunk/秒 |
| 典型耗時（1024×1024 格，3969 chunks）| 約 2–4 秒 |
| 加速方式 | numpy 向量化 section 計算 + 向量化 bit packing |

### 預覽系統

| 項目 | 說明 |
|------|------|
| 左圖 | 3D surface plot，含 LightSource 光照（方位 315°、仰角 45°） |
| 右圖 | 俯視 hillshade + 海平面（藍線）/ 雪線（白線）等高線 |
| 顏色映射 | 深海→淺海→沙灘→草地→森林→岩石→雪地（依 sea_level / snow_line 動態調整） |
| 降採樣 | 3D ≤ 256×256、2D ≤ 512×512（自動縮放） |
| 輸出 | `output/preview.png`（自動以系統預設程式開啟） |

### 座標系對應

```
圖片 (px, pz)  →  MC 世界 (origin_x + px × scale,  origin_z + pz × scale)
圖片水平（→）  →  MC +X 方向
圖片垂直（↓）  →  MC +Z 方向（面朝南）
左上角         →  西北角（面朝北時的左上角）
```

---

## 注意事項

1. **進入遊戲前**，請確認 Minecraft 已完全關閉，否則存檔可能被遊戲覆蓋。
2. `output/` 每次執行都會**完整覆蓋**，若有需要請先備份。
3. 工具會覆蓋指定範圍內的**所有現有方塊**（含建築、樹木等）。
4. 目前不支援 Bedrock 版（LevelDB 格式）。
5. `--x` / `--z` 與 `--region-origin` 同時指定時，`--x` / `--z` 優先。
