# -*- coding: utf-8 -*-
"""趁气泡坏着，把现场抓下来：窗口在不在、可见不可见、位置对不对。"""
import ctypes
import json
import os
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000

DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
STATE = os.path.join(DSH_HOME, "storages", "feiyu-chat")


def info(title, hwnd):
    print(f"\n== {title} ==")
    if not hwnd:
        print("  窗口不存在（FindWindow 返回 0）")
        return
    name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, name, 256)
    text = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, text, 256)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    print(f"  hwnd={hwnd}  IsWindow={bool(user32.IsWindow(hwnd))}  Visible={bool(user32.IsWindowVisible(hwnd))}")
    print(f"  class={name.value!r}  title={text.value!r}")
    print(f"  rect=({rect.left},{rect.top})-({rect.right},{rect.bottom})  宽高={rect.right-rect.left}x{rect.bottom-rect.top}")
    print(f"  exstyle=0x{ex & 0xFFFFFFFF:08X}  TOPMOST={bool(ex & WS_EX_TOPMOST)}  LAYERED={bool(ex & WS_EX_LAYERED)}")


def file_stamp(path):
    try:
        m = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return m, data
    except Exception as e:
        return None, e


def main():
    now = time.time()
    print("现在:", time.strftime("%H:%M:%S", time.localtime(now)))

    for label, cls in (
        ("桌宠窗口", "feiyu-chat-companion"),
        ("气泡窗口", "feiyu-chat-companion-bubble"),
    ):
        info(label, user32.FindWindowW(cls, None))

    print("\n== 文件 ==")
    for name in ("say.json", "foreground.json", "control.json", "debug.json"):
        path = os.path.join(STATE, name)
        m, data = file_stamp(path)
        if m is None:
            print(f"  {name}: 读不到 ({data})")
            continue
        age = now - m
        if isinstance(data, dict):
            brief = json.dumps(data, ensure_ascii=False)[:150]
        else:
            brief = str(data)[:150]
        print(f"  {name}: {age:6.1f} 秒前改过  {brief}")


if __name__ == "__main__":
    main()
