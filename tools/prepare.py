# -*- coding: utf-8 -*-
"""把两张真透明的桌宠图裁成同一尺寸。

两张 bbox 差 1～2 像素，各裁各的话眨眼时整只鱼会跳一下。
所以取联合 bbox，统一裁。
"""
import os

from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
PAIRS = [("open2.png", "open_rgba.png"), ("closed2.png", "closed_rgba.png")]

imgs = []
for src, _ in PAIRS:
    imgs.append(Image.open(os.path.join(SRC, src)).convert("RGBA"))

boxes = [im.getbbox() for im in imgs]
left = min(b[0] for b in boxes)
top = min(b[1] for b in boxes)
right = max(b[2] for b in boxes)
bottom = max(b[3] for b in boxes)
box = (left, top, right, bottom)
print("联合 bbox:", box, "->", right - left, "x", bottom - top)

for im, (_, dst) in zip(imgs, PAIRS):
    out = im.crop(box)
    out.save(os.path.join(SRC, dst))
    print("  ->", dst, out.size)
