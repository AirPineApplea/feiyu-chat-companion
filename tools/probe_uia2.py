# -*- coding: utf-8 -*-
"""测 UIA 读 Edge 视口文本：耗时多少、能读到什么。"""
import ctypes
import sys
import time
from ctypes import wintypes

import uiautomation as auto

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_edge():
    found = []

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value
        if title and "Edge" in title:
            found.append((hwnd, title))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found


wins = find_edge()
if not wins:
    print("没找到 Edge 窗口")
    sys.exit(0)
hwnd, title = wins[0]
print("窗口: %s" % title[:70])

texts = []
started = time.time()


def walk(ctrl, depth):
    if depth > 7 or len(texts) >= 40:
        return
    try:
        children = ctrl.GetChildren()
    except Exception:
        return
    for child in children:
        if len(texts) >= 40:
            return
        try:
            if child.ControlTypeName == "TextControl":
                name = (child.Name or "").strip()
                if name:
                    off = False
                    try:
                        off = bool(child.IsOffscreen)
                    except Exception:
                        pass
                    if not off:
                        texts.append(name)
        except Exception:
            pass
        walk(child, depth + 1)


try:
    win = auto.ControlFromHandle(hwnd)
    walk(win, 0)
except Exception as exc:
    print("失败: %r" % (exc,))
    sys.exit(1)

print("耗时 %.2f 秒，读到 %d 块（非屏外）" % (time.time() - started, len(texts)))
for line in texts[:12]:
    print("  · " + line[:70])
