# -*- coding: utf-8 -*-
"""把桌宠进程的所有窗口列出来（按 PID），不看类名猜。输出强制 UTF-8。"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080


def _cls(hwnd):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    return b.value


def _text(hwnd):
    b = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, b, 512)
    return b.value


def _pid(hwnd):
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


def enum_all():
    rows = []

    @WNDENUMPROC
    def cb(hwnd, _l):
        rows.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return rows


def dump(target_pid):
    print(f"枚举全部顶层窗口，筛 PID={target_pid}")
    hit = 0
    for hwnd in enum_all():
        if _pid(hwnd) != target_pid:
            continue
        hit += 1
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
        print(f"  hwnd={hwnd} class={_cls(hwnd)!r}")
        print(f"    title={_text(hwnd)!r}")
        print(f"    visible={bool(user32.IsWindowVisible(hwnd))}  "
              f"rect=({rect.left},{rect.top})-({rect.right},{rect.bottom}) "
              f"尺寸={rect.right - rect.left}x{rect.bottom - rect.top}")
        print(f"    exstyle=0x{ex:08X} TOPMOST={bool(ex & WS_EX_TOPMOST)} "
              f"LAYERED={bool(ex & WS_EX_LAYERED)} TOOLWIN={bool(ex & WS_EX_TOOLWINDOW)}")
    if hit == 0:
        print("  （这个进程没有任何顶层窗口）")
    return hit


def main():
    dsh_home = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
    state = os.path.join(dsh_home, "storages", "feiyu-chat")
    pid_path = os.path.join(state, "pet.pid")
    try:
        with open(pid_path, "r", encoding="utf-8") as fh:
            pid = int(fh.read().strip())
    except Exception as e:
        print("读不到 pet.pid:", e)
        return

    now = time.time()
    print("现在:", time.strftime("%H:%M:%S", time.localtime(now)), " pet.pid =", pid)

    # 进程还活着吗
    handle = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
    print("进程存活:", bool(handle))
    if handle:
        kernel32.CloseHandle(handle)

    dump(pid)


if __name__ == "__main__":
    main()
