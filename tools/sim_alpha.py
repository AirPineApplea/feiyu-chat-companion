# -*- coding: utf-8 -*-
"""模拟「直通 alpha」和「预乘 alpha」叠在深色桌面上的差别。

背景：UpdateLayeredWindow + AC_SRC_ALPHA 要求位图**预乘**过 alpha。
喂直通 alpha 进去，合成公式会当成预乘来算 —— 边缘每个半透明像素都偏亮，
在深色桌面上就是一圈白边。

这里按 Windows 的实际公式（预乘语义）把两种输入各算一次，缩到真实显示尺寸，
再各切一块放大，摆一起看。
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
DISPLAY_H = 75                      # 屏幕上大约这么高
BG = (26, 28, 34)                   # 深色桌面
ZOOM = 4


def load(name):
    arr = np.asarray(Image.open(os.path.join(ASSETS, name)).convert("RGBA")).astype(np.float32)
    alpha = arr[:, :, 3].astype(np.int16)
    bright = arr[:, :, :3].mean(axis=2)
    arr[(alpha < 90) & (bright > 170), 3] = 0     # 和 load_rgba 里那条阈值一致
    return arr


def resize_straight(arr, h):
    img = Image.fromarray(arr.astype(np.uint8), "RGBA")
    w = max(1, int(round(img.width * (h / img.height))))
    return np.asarray(img.resize((w, h), Image.LANCZOS)).astype(np.float32)


def resize_premul(arr, h):
    a = arr[:, :, 3:4] / 255.0
    pre = arr.copy()
    pre[:, :, :3] *= a
    img = Image.fromarray(pre.astype(np.uint8), "RGBA")
    w = max(1, int(round(img.width * (h / img.height))))
    return np.asarray(img.resize((w, h), Image.LANCZOS)).astype(np.float32)


def composite_premul_buggy(src, bg=BG):
    """Windows 把源当成预乘来合成，但源其实是直通的 —— 这就是现在的样子。"""
    a = src[:, :, 3:4] / 255.0
    dst = np.array(bg, dtype=np.float32).reshape(1, 1, 3)
    return np.clip(src[:, :, :3] + (1.0 - a) * dst, 0, 255)


def composite_premul_ok(src, bg=BG):
    """源已经是预乘的（RGB 已乘过 alpha），合成正确。"""
    a = src[:, :, 3:4] / 255.0
    dst = np.array(bg, dtype=np.float32).reshape(1, 1, 3)
    return np.clip(src[:, :, :3] + (1.0 - a) * dst, 0, 255)


def edge_crop(rgb, x0, w=46, h=100):
    return rgb[:, max(0, x0 - 4):max(0, x0 - 4) + w, :]


def main():
    arr = load("open_rgba.png")

    straight = resize_straight(arr, DISPLAY_H)
    premul = resize_premul(arr, DISPLAY_H)

    now = composite_premul_buggy(straight)
    fixed = composite_premul_ok(premul)

    # 找最左边那条边缘，用来放大
    alpha_cols = np.where((premul[:, :, 3] > 8).any(axis=0))[0]
    x0 = int(alpha_cols[0]) if len(alpha_cols) else 0

    tiles = []
    for rgb, label in ((now, "now"), (fixed, "fixed")):
        full = Image.fromarray(rgb.astype(np.uint8), "RGB")
        tiles.append(("full", full))
        crop = Image.fromarray(edge_crop(rgb, x0).astype(np.uint8), "RGB")
        tiles.append(("crop", crop.resize((crop.width * ZOOM, crop.height * ZOOM), Image.NEAREST)))

    pad = 12
    width = sum(t.width for _, t in tiles) + pad * (len(tiles) + 1)
    height = max(t.height for _, t in tiles) + pad * 2
    canvas = Image.new("RGB", (width, height), BG)
    x = pad
    for _, t in tiles:
        canvas.paste(t, (x, (height - t.height) // 2))
        x += t.width + pad

    out = os.path.join(ASSETS, "alpha_compare.png")
    canvas.save(out, "PNG")

    # 顺手量一下：边缘那一圈的亮度差
    def edge_lum(rgb, alpha):
        m = (alpha > 8) & (alpha < 248)
        return rgb[m].mean() if m.any() else float("nan")

    print(f"显示高度 {DISPLAY_H}px  放大 {ZOOM}x")
    print(f"  现在  边缘平均亮度 {edge_lum(now, premul[:, :, 3]):.1f}")
    print(f"  修完  边缘平均亮度 {edge_lum(fixed, premul[:, :, 3]):.1f}")
    print(f"  对比图 -> {out}")


if __name__ == "__main__":
    main()
