# -*- coding: utf-8 -*-
"""桌宠窗口：一只永远在屏幕上、能被拖动、撞边不出去的鱼。

几个坑（都已经踩过并绕开）：
  · tkinter 的 geometry 改完必须 update_idletasks，否则窗口根本不挪
  · Tk() 一构造就抢前台焦点，建完要把焦点还给原来的窗口
  · 透明靠 -transparentcolor 抠背景色，图片得先合成到同一个色上
"""
import ctypes
import os
import sys
import tkinter as tk

from PIL import Image, ImageTk

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
KEY = "#ff00ff"          # 洋红做抠色，角色身上没有这个色
PET_HEIGHT = 220         # 屏幕上的高度（宽按比例）

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SPI_GETWORKAREA = 0x0030


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def work_area():
    rect = RECT()
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        if ok and rect.right > rect.left:
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    w = ctypes.windll.user32.GetSystemMetrics(0)
    h = ctypes.windll.user32.GetSystemMetrics(1)
    return 0, 0, w, h


def restore_foreground(hwnd):
    """把焦点还给桌宠窗口创建之前的那个窗口（Tk() 会抢）。"""
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    try:
        current = user32.GetForegroundWindow()
        if current == hwnd:
            return
        cur_t = user32.GetWindowThreadProcessId(current, None)
        dst_t = user32.GetWindowThreadProcessId(hwnd, None)
        attached = False
        if cur_t and dst_t and cur_t != dst_t:
            attached = bool(user32.AttachThreadInput(cur_t, dst_t, True))
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(cur_t, dst_t, False)
    except Exception:
        pass


def load_pet(path):
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    scale = PET_HEIGHT / float(h)
    nw = max(1, int(round(w * scale)))
    img = img.resize((nw, PET_HEIGHT), Image.LANCZOS)
    plate = Image.new("RGBA", img.size, (255, 0, 255, 255))
    plate.alpha_composite(img)
    return plate.convert("RGB")


class Pet(object):
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("feiyu-chat-companion")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", KEY)
        self.root.configure(bg=KEY)

        self.photo = ImageTk.PhotoImage(load_pet(os.path.join(ASSETS, "idle_rgba.png")))
        self.label = tk.Label(self.root, image=self.photo, bd=0, bg=KEY)
        self.label.pack()

        self.w = self.photo.width()
        self.h = self.photo.height()
        self.left, self.top, self.right, self.bottom = work_area()

        # 初始位置：右下角，离任务栏留一点
        x = self.right - self.w - 24
        y = self.bottom - self.h - 8
        self.root.geometry("%dx%d+%d+%d" % (self.w, self.h, x, y))
        self.root.update_idletasks()

        self._drag = None
        for widget in (self.root, self.label):
            widget.bind("<Button-1>", self.on_press)
            widget.bind("<B1-Motion>", self.on_drag)
            widget.bind("<ButtonRelease-1>", self.on_release)
            widget.configure(cursor="hand2")

        self._make_noactivate()
        prev = ctypes.windll.user32.GetForegroundWindow()
        self.root.update_idletasks()
        restore_foreground(prev)

    def _make_noactivate(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        except Exception:
            pass

    # ---------- 拖动 ----------

    def on_press(self, event):
        self._drag = (event.x_root, event.y_root,
                      self.root.winfo_x(), self.root.winfo_y())

    def on_drag(self, event):
        if self._drag is None:
            return
        dx = event.x_root - self._drag[0]
        dy = event.y_root - self._drag[1]
        x = self._drag[2] + dx
        y = self._drag[3] + dy
        # 撞边不出去：整只鱼必须留在工作区里
        x = max(self.left, min(x, self.right - self.w))
        y = max(self.top, min(y, self.bottom - self.h))
        self.root.geometry("+%d+%d" % (x, y))
        self.root.update_idletasks()

    def on_release(self, event):
        self._drag = None

    def run(self):
        self.root.mainloop()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    Pet().run()


if __name__ == "__main__":
    main()
