# -*- coding: utf-8 -*-
"""回归测试：连续显示两个**不同尺寸**的气泡。

这就是那个 bug 的触发条件 —— 尺寸变化时 `_upload` 会删除旧 DC，
而 `DeleteDC` 当时没声明 argtypes，64 位句柄一传就 OverflowError，
异常被 ctypes 吞掉，那一句永久丢。
"""
import importlib.util
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
    bubble = mod.Bubble()
    print(f"Bubble hwnd={bubble.hwnd}")

    texts = [
        "短",
        "这一句明显更长一些，宽度一定和上一句不一样，所以必然要重建 DC。",
        "又短了",
        "再来一句长度不同的，逼它再删一次 DC。",
    ]

    ok = 0
    for i, text in enumerate(texts, 1):
        img = mod.render_bubble(text)
        try:
            bubble.show(img, 100 + i * 10, 100, 30.0)
            bubble.tick()
            print(f"  [{i}] 尺寸 {img.size} -> show OK  visible={bubble.visible}")
            ok += 1
        except Exception:
            print(f"  [{i}] 尺寸 {img.size} -> 炸了：")
            traceback.print_exc()
            return 1
        time.sleep(0.1)

    print(f"\n{ok}/{len(texts)} 次成功")
    return 0 if ok == len(texts) else 1


if __name__ == "__main__":
    sys.exit(main())
