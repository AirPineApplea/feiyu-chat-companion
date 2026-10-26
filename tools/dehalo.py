# -*- coding: utf-8 -*-
"""去掉边缘那圈"被白底冲淡"的颜色（decontamination）。

原理：原图是白底合成的，边缘像素 P = a·F + (1-a)·白。
现有的 *_rgba.png 只存了 alpha，颜色还是 P —— 所以边缘那圈永远是浅的。
反解：F = (P - (1-a)·白) / a。

注意别在已经反解过的图上再算一遍（会越算越黑）。
所以颜色一律从**原始合成图**（open2/closed2）里取，alpha 从现有的 rgba 里取。
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")


def decontaminate(src_path, out_path, bg=(255, 255, 255)):
    """src 里的 RGB 还是白底合成的（alpha 才是抠出来的），所以就地反解。"""
    src = Image.open(src_path).convert("RGBA")
    arr = np.asarray(src).astype(np.float32)

    alpha = arr[:, :, 3]
    a = (alpha / 255.0)[:, :, None]
    bgv = np.array(bg, dtype=np.float32).reshape(1, 1, 3)
    safe = np.maximum(a, 0.004)          # 全透明处不参与，别除出天文数字
    fg = (arr[:, :, :3] - bgv * (1.0 - a)) / safe
    fg = np.clip(fg, 0, 255)

    out = np.zeros_like(arr)
    out[:, :, :3] = fg
    out[:, :, 3] = alpha
    Image.fromarray(out.astype(np.uint8), "RGBA").save(out_path, "PNG")

    edge = (alpha > 8) & (alpha < 248)
    before = arr[:, :, :3].mean(axis=2)[edge].mean()
    after = fg.mean(axis=2)[edge].mean()
    print(f"  {os.path.basename(out_path)}  边缘像素 {int(edge.sum())}  "
          f"平均亮度 {before:.1f} -> {after:.1f}")


def preview(alpha_path, pairs, out_path, scale_h=220, bg=(24, 24, 28)):
    """三栏对比：原样 / 反解后，都缩到显示尺寸，垫在深色底上看。"""
    tiles = []
    for label_path in pairs:
        img = Image.open(label_path).convert("RGBA")
        w = int(img.width * scale_h / img.height)
        tiles.append(img.resize((w, scale_h), Image.LANCZOS))

        # 局部放大：取最左边那条边缘
        arr = np.asarray(img)[:, :, 3]
        cols = np.where((arr > 8).any(axis=0))[0]
        x0 = int(cols[0]) if len(cols) else 0
        crop = img.crop((max(0, x0 - 6), img.height // 2 - 60, x0 + 60, img.height // 2 + 60))
        tiles.append(crop.resize((crop.width * 3, crop.height * 3), Image.NEAREST))

    pad = 16
    width = sum(t.width for t in tiles) + pad * (len(tiles) + 1)
    height = max(t.height for t in tiles) + pad * 2
    canvas = Image.new("RGBA", (width, height), bg + (255,))
    x = pad
    for t in tiles:
        canvas.alpha_composite(t, (x, (height - t.height) // 2))
        x += t.width + pad
    canvas.save(out_path, "PNG")
    print(f"  对比图 -> {out_path}")


def main():
    jobs = [
        ("open_rgba.png", "open_dehalo.png"),
        ("closed_rgba.png", "closed_dehalo.png"),
    ]
    for src, out in jobs:
        s = os.path.join(ASSETS, src)
        o = os.path.join(ASSETS, out)
        if not os.path.exists(s):
            print(f"跳过 {src} 缺文件")
            continue
        print(f"处理 {src}")
        decontaminate(s, o)

    before = os.path.join(ASSETS, "open_rgba.png")
    after = os.path.join(ASSETS, "open_dehalo.png")
    if os.path.exists(after):
        preview(None, [before, after], os.path.join(ASSETS, "halo_compare.png"))


if __name__ == "__main__":
    main()
