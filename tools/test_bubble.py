# -*- coding: utf-8 -*-
"""在独立进程里跑一遍 render_bubble + Bubble.show()，把异常露出来。

桌宠进程里这些异常被 ctypes 吞掉了（还打在 stderr 上，而桌宠是 stdio:ignore 起的，
等于全丢）。这里复现一次，看看到底哪行炸。
"""
import importlib.util
import os
import sys
import time
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MOD = r"D:\dsh-web-pet\overlay\pet_win32.py"


def load_module():
    spec = importlib.util.spec_from_file_location("petmod", MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    mod = load_module()
    print("模块加载完成")

    text = "测试气泡：能看见我吗"
    try:
        img = mod.render_bubble(text)
        print(f"render_bubble OK  尺寸={img.size} 模式={img.mode}")
    except Exception:
        print("render_bubble 炸了：")
        traceback.print_exc()
        return

    try:
        bubble = mod.Bubble()
        print(f"Bubble OK  hwnd={bubble.hwnd}")
    except Exception:
        print("Bubble() 炸了：")
        traceback.print_exc()
        return

    if not bubble.hwnd:
        print("!! CreateWindowExW 返回 0（窗口没创建出来），GetLastError 见下")
        return

    try:
        bubble.show(img, 100, 100, 20.0)
        print(f"show OK  visible={bubble.visible}  hide_at 还有 {bubble.hide_at - time.time():.1f} 秒")
    except Exception:
        print("show() 炸了：")
        traceback.print_exc()
        return

    # 让它真显示 5 秒，方便外面探测
    deadline = time.time() + 5
    while time.time() < deadline:
        bubble.tick()
        time.sleep(0.05)
    print("结束")


if __name__ == "__main__":
    main()
