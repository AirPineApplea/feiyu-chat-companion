# -*- coding: utf-8 -*-
"""把棋盘格假透明背景抠成真 alpha。

关键：先用颜色条件二值化出「候选背景」，再在这张单通道图上从四角灌色。
直接在彩色图上灌不行 —— PIL 比的是打包后的整数值，232 和 254 差一百多万，
跨不过格子。二值化之后整片候选都是 255，一路通到底。
角色身上的纯白（围裙）不会被误吃，因为它跟图片边界不连通。
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


def cut(name):
    path = os.path.join(SRC, name)
    img = Image.open(path).convert("RGB")
    w, h = img.size
    rgb = np.array(img)

    lo = rgb.min(axis=2).astype(np.int16)
    hi = rgb.max(axis=2).astype(np.int16)
    # 浅色 + 无彩（棋盘格两种灰都是 R=G=B）
    cand = ((lo >= 218) & ((hi - lo) <= 10)).astype(np.uint8) * 255

    # fromarray 出来的 image 是只读的，floodfill 会静默失败——必须 copy()
    mask = Image.fromarray(cand, "L").copy()
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if mask.getpixel(corner) == 255:
            ImageDraw.floodfill(mask, corner, 128, thresh=0)

    bg = np.array(mask) == 128
    rgba = np.dstack([rgb, np.full((h, w), 255, np.uint8)])
    rgba[bg] = (0, 0, 0, 0)

    out = Image.fromarray(rgba, "RGBA")
    # 边缘那圈是「角色色 + 棋盘格」的抗锯齿混合，留着就是一圈白边。
    # 把 alpha 向内收 1 像素再轻微羽化，白边就没了。
    alpha = out.getchannel("A").filter(ImageFilter.MinFilter(3))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    out.putalpha(alpha)
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return out, int(bg.sum())


for src, dst in [("idle.png", "idle_rgba.png"), ("blink.png", "blink_rgba.png")]:
    out, n = cut(src)
    out.save(os.path.join(SRC, dst))
    print("%s -> %s  %dx%d  去掉背景 %d 像素 (%.1f%%)" % (
        src, dst, out.size[0], out.size[1], n, n * 100.0 / (1024 * 1024)))
