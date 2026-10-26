# -*- coding: utf-8 -*-
"""测一下用 UIA 读前台浏览器视口文本要多久、能读到什么。"""
import ctypes
import sys
import time

import uiautomation as auto

user32 = ctypes.windll.user32


def foreground():
    hwnd = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return hwnd, buf.value.strip()


def collect(hwnd, limit=40):
    texts = []
    try:
        win = auto.ControlFromHandle(hwnd)
    except Exception as exc:
        return "取窗口失败: %r" % (exc,), 0.0
    started = time.time()

    def walk(ctrl, depth):
        if depth > 7 or len(texts) >= limit:
            return
        try:
            children = ctrl.GetChildren()
        except Exception:
            return
        for child in children:
            if len(texts) >= limit:
                return
            try:
                if child.ControlTypeName == "TextControl":
                    name = (child.Name or "").strip()
                    if name and not child.IsOffscreen:
                        texts.append(name)
            except Exception:
                pass
            walk(child, depth + 1)

    walk(win, 0)
    return texts, time.time() - started


hwnd, title = foreground()
print("前台: %s" % title)
result, took = collect(hwnd)
if isinstance(result, str):
    print(result)
else:
    print("耗时 %.2f 秒，读到 %d 块" % (took, len(result)))
    for line in result[:15]:
        print("  · " + line[:80])
