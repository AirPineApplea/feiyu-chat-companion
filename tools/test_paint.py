# -*- coding: utf-8 -*-
"""验证桌宠本体的绘制原语在补齐原型之后还通：GetDC / DIB / UpdateLayeredWindow / 清理。

不碰 state.json、foreground.json，也不显示真鱼 —— 只建一个 8x8 的透明窗口走一遍。
"""
import importlib.util
import sys

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MOD = r"D:\dsh-web-pet\overlay\pet_win32.py"


def main():
    spec = importlib.util.spec_from_file_location("petmod", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    user32, gdi32 = mod.user32, mod.gdi32
    ctypes = mod.ctypes

    # 先用桌宠自己的 load_rgba 产出预乘 BGRA
    import os
    size, bgra = mod.load_rgba(os.path.join(r"D:\dsh-web-pet\assets", "open_rgba.png"), mod.PET_HEIGHT)
    print(f"load_rgba OK  尺寸={size}  bgra={bgra.shape} {bgra.dtype}")

    w, h = size
    hdc_screen = user32.GetDC(None)
    print(f"GetDC -> {hdc_screen!r}  (64 位句柄不该被截断)")

    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bmi = mod.BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(mod.BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = mod.BI_RGB
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    print(f"CreateDIBSection -> hbmp={hbmp!r} bits={bool(bits.value)}")
    gdi32.SelectObject(hdc_mem, hbmp)
    ctypes.memmove(bits, bgra.tobytes(), bgra.nbytes)

    # 建一个 layered popup 窗口
    hinst = mod.kernel32.GetModuleHandleW(None)
    cls = "HalveTestWnd"
    wc = mod.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(mod.WNDCLASSEXW)
    wc.lpfnWndProc = mod.WNDPROC(lambda a, b, c, d: user32.DefWindowProcW(a, b, c, d))
    wc.hInstance = hinst
    wc.lpszClassName = cls
    user32.RegisterClassExW(ctypes.byref(wc))
    ex = mod.WS_EX_LAYERED | mod.WS_EX_TOOLWINDOW | mod.WS_EX_NOACTIVATE
    hwnd = user32.CreateWindowExW(ex, cls, "halo-test", mod.WS_POPUP, 0, 0, 8, 8, None, None, hinst, None)
    print(f"CreateWindowExW -> hwnd={hwnd!r}")

    pt_dst = mod.POINT(50, 50)
    pt_src = mod.POINT(0, 0)
    sz = mod.SIZE(w, h)
    blend = mod.BLENDFUNCTION(mod.AC_SRC_OVER, 0, 255, mod.AC_SRC_ALPHA)
    ok = user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(sz),
                                    hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend),
                                    mod.ULW_ALPHA)
    print(f"UpdateLayeredWindow 返回 {ok}（1 = 成功）")

    user32.DestroyWindow(hwnd)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    print("清理 DeleteObject / DeleteDC 没有报错 —— 这就是之前炸的那两行")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
