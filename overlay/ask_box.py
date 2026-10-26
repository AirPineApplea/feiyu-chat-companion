# -*- coding: utf-8 -*-
"""问她一句 —— 右键桌宠弹出来的单行输入框。

为什么是独立进程：
  桌宠本体是一个跑着 Win32 消息循环的 layered 窗口。tkinter 自己也要一个事件循环，
  两套循环塞进一个进程会互相卡。这里就开一个一次性进程，问完、写完、退出，
  崩了也只崩这个小框，不连累桌宠。

为什么不用 overrideredirect 的无边框：那种窗口在 Windows 上经常拿不到键盘焦点，
  输进去的字会飘到别的窗口。用 -toolwindow（有标题栏、不占任务栏）焦点是稳的。

提交 = 把问题写进 ask.json，Host 那边 500ms 轮询一次接走。
"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

import tkinter as tk
from tkinter import font as tkfont

BG = "#16202e"
FG = "#eaf2ff"
SUBTLE = "#8fa6c4"
ACCENT = "#6096e0"
EDGE = "#2a3a52"

WIDTH = 380
HEIGHT = 128


def dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def cursor_pos():
    pt = wintypes.POINT()
    try:
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 200, 200


def write_ask(state_dir, text):
    """原子写：先写临时文件再 replace，别让 Host 读到半个 JSON。"""
    payload = {"seq": int(time.time() * 1000), "text": text, "at": int(time.time() * 1000)}
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, "ask.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    if len(sys.argv) < 2:
        return 2
    state_dir = sys.argv[1]
    dpi_aware()

    root = tk.Tk()
    root.title("问她一句")
    root.configure(bg=BG)
    root.resizable(False, False)
    try:
        root.attributes("-toolwindow", True)
    except Exception:
        pass
    root.attributes("-topmost", True)

    cx, cy = cursor_pos()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = max(0, min(cx - WIDTH // 2, screen_w - WIDTH - 8))
    y = max(0, min(cy - HEIGHT - 24, screen_h - HEIGHT - 8))
    root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    label = tk.Label(
        root, text="问她一句，回车发送", bg=BG, fg=SUBTLE,
        font=(tkfont.nametofont("TkDefaultFont").actual("family"), 9), anchor="w",
    )
    label.pack(fill="x", padx=14, pady=(10, 0))

    var = tk.StringVar()
    entry = tk.Entry(
        root, textvariable=var, bg="#0f1622", fg=FG, insertbackground=FG,
        relief="flat", highlightthickness=1, highlightbackground=EDGE,
        highlightcolor=ACCENT, font=(tkfont.nametofont("TkDefaultFont").actual("family"), 12),
    )
    entry.pack(fill="x", padx=14, pady=(6, 0), ipady=7)

    hint = tk.Label(root, text="Esc 关掉", bg=BG, fg=SUBTLE, anchor="w",
                    font=(tkfont.nametofont("TkDefaultFont").actual("family"), 9))
    hint.pack(fill="x", padx=14, pady=(6, 0))

    def submit(_event=None):
        text = var.get().strip()
        if text == "":
            return "break"
        try:
            write_ask(state_dir, text)
        except Exception:
            return "break"
        root.destroy()
        return "break"

    def close(_event=None):
        root.destroy()
        return "break"

    entry.bind("<Return>", submit)
    root.bind("<Escape>", close)
    root.protocol("WM_DELETE_WINDOW", close)

    # 焦点要抢，不然输进去的字会跑到别的窗口
    root.after(60, lambda: (root.lift(), root.focus_force(), entry.focus_force()))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
