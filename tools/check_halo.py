# -*- coding: utf-8 -*-
"""量一下桌宠素材的"白边"到底剩多少。

白边的本质：原图是白底合成的，边缘那圈像素是「角色色 × alpha + 白色 × (1-alpha)」。
抠图只留了 alpha，颜色没反解，于是边缘那圈永远是「角色色被白色冲淡过」的浅色，
显示在深色桌面上就成了一圈白线。
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")


def report(name):
    path = os.path.join(ASSETS, name)
    if not os.path.exists(path):
        print(f"{name}: 不存在")
        return
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3].astype(np.int16)
    rgb = arr[:, :, :3].astype(np.int16)

    total = arr.shape[0] * arr.shape[1]
    opaque = int((alpha > 250).sum())
    clear = int((alpha == 0).sum())
    edge = int(((alpha > 0) & (alpha <= 250)).sum())

    # 半透明且偏亮 —— 白边的主要嫌疑
    lum = rgb.mean(axis=2)
    bright_edge = int(((alpha > 0) & (alpha <= 250) & (lum > 200)).sum())
    # 完全不透明但几乎是白的（描边被烤死）
    white_solid = int(((alpha > 250) & (rgb.min(axis=2) > 235)).sum())

    print(f"\n== {name}  {img.size[0]}x{img.size[1]} ==")
    print(f"  总像素 {total}")
    print(f"  全透明 {clear}  半透明 {edge}  不透明 {opaque}")
    print(f"  半透明且亮(>200) {bright_edge}   <- 白边嫌疑")
    print(f"  不透明但接近纯白  {white_solid}   <- 被烤死的白描边")


for name in sys.argv[1:] or ["open_rgba.png", "closed_rgba.png"]:
    report(name)
