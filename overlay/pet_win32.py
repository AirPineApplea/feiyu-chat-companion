# -*- coding: utf-8 -*-
"""桌宠窗口（Win32 layered，真 alpha 合成）。

为什么不用 tkinter：
  -transparentcolor 只能抠一整个纯色，角色边缘的抗锯齿像素是「角色色 + 背景色」
  的混合，抠不掉，会留一圈洋红描边。UpdateLayeredWindow 才能真正按 alpha 混合。

行为：永远置顶、不抢焦点、不占任务栏、能拖、撞边不出去。
右键 = 退出。
"""
import ctypes
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
PET_HEIGHT = 113          # 图片像素高度；系统 150% 缩放后落到屏幕上是 ~75

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
BUBBLE_FONT_SIZE = 13
BUBBLE_MAX_W = 210
BUBBLE_PAD = 11
BUBBLE_BG = (22, 34, 54, 236)
BUBBLE_BORDER = (96, 150, 224, 255)
BUBBLE_FG = (234, 242, 255, 255)

DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")
STATE_DIR = os.path.join(DSH_HOME, "storages", "feiyu-chat")
STATE_PATH = os.path.join(STATE_DIR, "state.json")
PID_PATH = os.path.join(STATE_DIR, "pet.pid")
SAY_PATH = os.path.join(STATE_DIR, "say.json")
CONTROL_PATH = os.path.join(STATE_DIR, "control.json")
FOREGROUND_PATH = os.path.join(STATE_DIR, "foreground.json")


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data):
    """原子写：先写 .tmp 再 replace，半路断电不会留个坏文件。"""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)
    except Exception:
        pass


def _alive(pid):
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259               # STILL_ACTIVE
    except Exception:
        return False


def claim_instance():
    """已经有一只鱼在跑就不再启动第二只。"""
    try:
        if os.path.exists(PID_PATH):
            with open(PID_PATH, "r", encoding="utf-8") as handle:
                other = int((handle.read() or "0").strip() or 0)
            if other and other != os.getpid() and _alive(other):
                return False
    except Exception:
        pass
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(PID_PATH, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except Exception:
        pass
    return True

WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
HWND_TOPMOST = -1
SPI_GETWORKAREA = 0x0030
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
SW_HIDE = 0

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# 不显式声明的话，LPARAM 会被当 32 位，DefWindowProcW 直接报 OverflowError
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.RegisterClassExW.restype = wintypes.WORD

# GDI 的句柄在 64 位下是 64 位值（常见形如 0xFFFFFFFF9A0B1234）。
# 不声明 argtypes 的话 ctypes 按 32 位 int 收，传进去就
# "argument 1: OverflowError: int too long to convert" —— 而且会被 ctypes 静默吞掉。
# 踩过：气泡只在**尺寸变化**时才删旧 DC，于是同尺寸能显示、换个长度就永久丢一句。
# 这跟上面 DefWindowProcW 的 LPARAM 是同一个病根。
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]

user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ShowWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", wintypes.BYTE), ("BlendFlags", wintypes.BYTE),
                ("SourceConstantAlpha", wintypes.BYTE), ("AlphaFormat", wintypes.BYTE)]


# GetDC 现在按 64 位句柄返回，所以这里必须显式声明：两个 HDC 都要收得住，
# 否则会以同样的 OverflowError 在另一处炸掉。
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
    wintypes.HDC, ctypes.POINTER(POINT), wintypes.DWORD,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]


def work_area():
    r = RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0) and r.right > r.left:
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def load_rgba(path, target_h):
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)

    # 源图边缘有一圈「极低 alpha + 接近纯白」的光晕（抠图残留）。
    # 单看每个像素几乎看不见，但在深色背景上叠起来就是一整圈白雾。
    # 只杀「又淡又白」的，角色本身的半透明边不会中招。
    alpha = arr[:, :, 3].astype(np.int16)
    bright = arr[:, :, :3].mean(axis=2)
    halo = (alpha < 90) & (bright > 170)
    arr[halo, 3] = 0

    # 预乘 alpha 再缩放。两个理由：
    #   1) UpdateLayeredWindow + AC_SRC_ALPHA 要的是预乘位图。喂直通 alpha，
    #      每个半透明像素会被抬亮 (1-alpha)·色 —— 金属碗和围裙边上实测多亮
    #      177 个色阶，那就是「廉价白边」的真身。
    #   2) 先预乘再缩放，透明像素的黑 RGB 才不会渗进边缘把轮廓拉暗。
    straight = np.asarray(Image.fromarray(arr, "RGBA")).astype(np.float32)
    straight[:, :, :3] *= straight[:, :, 3:4] / 255.0
    out = Image.fromarray(straight.astype(np.uint8), "RGBA")
    w, h = out.size
    nw = max(1, int(round(w * (target_h / float(h)))))
    out = out.resize((nw, target_h), Image.LANCZOS)

    # 缩放会在轮廓上来回振铃，预乘之后可能出现「RGB 比 alpha 还大」的过冲点，
    # 那在屏幕上是几颗亮斑。夹回不变量里。
    scaled = np.array(out).astype(np.float32)
    scaled[:, :, :3] = np.minimum(scaled[:, :, :3], scaled[:, :, 3:4])

    bgra = np.ascontiguousarray(scaled.astype(np.uint8)[:, :, [2, 1, 0, 3]])   # DIB 要 BGRA（已预乘）
    return out.size, bgra


def _wrap(text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if font.getlength(cur + ch) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def render_bubble(text):
    try:
        font = ImageFont.truetype(FONT_PATH, BUBBLE_FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()
    lines = _wrap(str(text).strip()[:120], font, BUBBLE_MAX_W)
    widths = [font.getlength(line) for line in lines]
    line_h = BUBBLE_FONT_SIZE + 7
    tw = int(max(widths)) if widths else 40
    w = tw + BUBBLE_PAD * 2
    h = line_h * len(lines) + BUBBLE_PAD * 2

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=9,
                           fill=BUBBLE_BG, outline=BUBBLE_BORDER, width=1)
    y = BUBBLE_PAD
    for line in lines:
        draw.text((BUBBLE_PAD, y), line, font=font, fill=BUBBLE_FG)
        y += line_h
    return img


class Bubble(object):
    """头顶气泡：一个独立的 layered 小窗，显示一句话，几秒后自己消失。"""

    def __init__(self):
        self.hdc_screen = user32.GetDC(None)
        self.hdc_mem = None
        self.hbmp = None
        self.bits = None
        self.w = self.h = 0
        self.x = self.y = 0
        self.visible = False
        self.hide_at = 0.0

        # 回调必须留个引用，否则被 GC 掉会崩
        self._proc = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
        cls = "DshWebPetBubble"
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = cls
        user32.RegisterClassExW(ctypes.byref(wc))
        ex = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
        self.hwnd = user32.CreateWindowExW(
            ex, cls, "feiyu-chat-companion-bubble", WS_POPUP,
            0, 0, 8, 8, None, None, wc.hInstance, None)

    def _upload(self, img):
        # 预乘 alpha。UpdateLayeredWindow + AC_SRC_ALPHA 要的就是预乘位图，
        # 喂直通 alpha 会把每个半透明像素抬亮 (1-alpha)·色 —— 气泡的圆角边和字边
        # 也会因此有一圈亮边。
        arr = np.array(img).astype(np.float32)
        arr[:, :, :3] *= arr[:, :, 3:4] / 255.0
        bgra = np.ascontiguousarray(arr.astype(np.uint8)[:, :, [2, 1, 0, 3]])
        w, h = img.size
        if (w, h) != (self.w, self.h) or self.hdc_mem is None:
            if self.hbmp:
                gdi32.DeleteObject(self.hbmp)
            if self.hdc_mem:
                gdi32.DeleteDC(self.hdc_mem)
            self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = BI_RGB
            self.bits = ctypes.c_void_p()
            self.hbmp = gdi32.CreateDIBSection(
                self.hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
            gdi32.SelectObject(self.hdc_mem, self.hbmp)
            self.w, self.h = w, h
        ctypes.memmove(self.bits, bgra.tobytes(), bgra.nbytes)

    def _paint(self):
        if self.hdc_mem is None:
            return
        pt_dst = POINT(self.x, self.y)
        pt_src = POINT(0, 0)
        sz = SIZE(self.w, self.h)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(
            self.hwnd, self.hdc_screen, ctypes.byref(pt_dst), ctypes.byref(sz),
            self.hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)

    def show(self, img, x, y, duration=6.0):
        self._upload(img)
        self.x, self.y = x, y
        self._paint()
        user32.ShowWindow(self.hwnd, 8)
        self.visible = True
        self.hide_at = time.time() + duration

    def move_to(self, x, y):
        self.x, self.y = x, y
        if self.visible:
            self._paint()

    def tick(self):
        if self.visible and time.time() >= self.hide_at:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False


class Pet(object):
    def __init__(self, open_path, closed_path):
        # 两帧必须同尺寸，否则眨眼时整只鱼会跳；prepare.py 已经裁成联合 bbox
        self.frames = [load_rgba(open_path, PET_HEIGHT),
                       load_rgba(closed_path, PET_HEIGHT)]
        self.size, self.pixels = self.frames[0]
        self.frame_index = 0
        self.next_blink = time.time() + random.uniform(2.5, 5.0)
        self.blink_until = 0.0
        self.w, self.h = self.size
        self.left, self.top, self.right, self.bottom = work_area()

        # 位置记忆：上次拖到哪，这次还在哪；屏幕改过就夹回工作区
        self.state = load_state()
        self.muted = bool(self.state.get("muted"))
        sx, sy = self.state.get("x"), self.state.get("y")
        if isinstance(sx, int) and isinstance(sy, int):
            x = max(self.left, min(sx, self.right - self.w))
            y = max(self.top, min(sy, self.bottom - self.h))
        else:
            x = self.right - self.w - 30
            y = self.bottom - self.h - 10

        # --- 画布：带 alpha 的 32 位 DIB ---
        self.hdc_screen = user32.GetDC(None)
        self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = self.w
        bmi.biHeight = -self.h          # 负数 = 自上而下
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = BI_RGB
        self.bits = ctypes.c_void_p()
        self.hbmp = gdi32.CreateDIBSection(
            self.hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.hdc_mem, self.hbmp)
        ctypes.memmove(self.bits, self.pixels.tobytes(), self.pixels.nbytes)

        # --- 窗口 ---
        self.cls_name = "DshWebPetWnd"
        self.wndproc = WNDPROC(self._wndproc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self.wndproc
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_HAND 不对，用箭头更稳
        wc.lpszClassName = self.cls_name
        user32.RegisterClassExW(ctypes.byref(wc))

        ex = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
        self.hwnd = user32.CreateWindowExW(
            ex, self.cls_name, "feiyu-chat-companion", WS_POPUP,
            x, y, self.w, self.h, None, None, wc.hInstance, None)
        # 双保险：创建后再钉一次 TOPMOST，别的窗口置顶时也能爬回来
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

        self._paint(x, y)
        user32.ShowWindow(self.hwnd, 8)   # SW_SHOWNA
        user32.SetTimer(self.hwnd, 1, 60, None)   # 60ms 一次，够 100ms 的眨眼不出戏
        self.bubble = Bubble()
        self.say_mtime = -1.0
        self.say_seq = 0
        self.control_mtime = -1.0
        self.control_seq = 0
        self.probe_at = 0.0
        self.visible = True
        self.x, self.y = x, y
        self._drag = None

        # 地址栏探测跑在后台：UIA 读一次要 0.7 秒左右，塞进 60ms 的 tick 里会卡眨眼
        self.current_url = ""
        self.url_wanted = False
        self.url_stop = False
        self.url_thread = threading.Thread(target=self._url_worker, daemon=True)
        self.url_thread.start()

    # ---------- 地址栏（B站特化） ----------

    def _url_worker(self):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            import uiautomation as auto
        except Exception:
            return
        while not self.url_stop:
            time.sleep(0.4)
            if not self.url_wanted:
                continue
            self.url_wanted = False
            try:
                hwnd = user32.GetForegroundWindow()
                if not hwnd or hwnd == self.hwnd:
                    continue
                win = auto.ControlFromHandle(hwnd)
                self.current_url = self._find_address(win)
            except Exception:
                self.current_url = ""

    @staticmethod
    def _find_address(ctrl, depth=0):
        """在浏览器窗口里找地址栏。读不到就返回空串。"""
        if depth > 12:
            return ""
        try:
            children = ctrl.GetChildren()
        except Exception:
            return ""
        for child in children:
            try:
                if child.ControlTypeName == "EditControl" and child.Name == "地址和搜索栏":
                    try:
                        return (child.GetValuePattern().Value or "").strip()
                    except Exception:
                        return ""
            except Exception:
                pass
            found = Pet._find_address(child, depth + 1)
            if found:
                return found
        return ""

    def _bubble_pos(self, bw, bh):
        bx = self.x + (self.w - bw) // 2
        by = self.y - bh - 6
        if by < self.top:                    # 顶到屏幕外就翻到脚下
            by = self.y + self.h + 6
        bx = max(self.left, min(bx, self.right - bw))
        return bx, by

    def _log(self, msg):
        """往 pet.log 追加一行。

        为什么需要：_tick 是在 ctypes 回调里跑的，抛异常会被静默吞掉（只打一行到
        stderr，而桌宠是 stdio:ignore 起的，那行也丢了）。出了问题就是黑箱。
        """
        try:
            path = os.path.join(STATE_DIR, "pet.log")
            try:
                if os.path.getsize(path) > 512 * 1024:
                    os.replace(path, path + ".1")
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%H:%M:%S ") + msg + "\n")
        except Exception:
            pass

    def _show_bubble(self, text, duration=6.0):
        img = render_bubble(text)
        bx, by = self._bubble_pos(img.size[0], img.size[1])
        self._log(f"气泡 {img.size} @({bx},{by}) {duration:.1f}s 「{text[:24]}」")
        self.bubble.show(img, bx, by, duration)
        self._log(f"  显示后 visible={self.bubble.visible}")

    def _check_say(self):
        try:
            stamp = os.path.getmtime(SAY_PATH)
        except OSError:
            return
        if stamp == self.say_mtime:
            return
        try:
            with open(SAY_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            # 记账放到解析成功之后：Host 现在已经是原子写了，但万一还是撞上
            # 半截文件，这一句不能就此永久丢掉 —— 下一轮还要再试。
            self._log(f"读 say.json 失败（{exc}），不记账，下次重试")
            return
        self.say_mtime = stamp
        text = str(data.get("text") or "").strip()
        if not text:
            return
        # 不用 seq 做去重：Host 重启会归零，人工写一次乱序值也会把它永久卡住
        # （踩过两次）。只认「文件变过没」，mtime 变了就是新的一句话。
        if self.muted:
            self._log("静音中，这句跳过")
            return      # 静音时读掉但不播：恢复后不会一口气涌出来
        self._show_bubble(text, float(data.get("duration") or 6.0))

    def _set_frame(self, index):
        if index == self.frame_index:
            return
        self.frame_index = index
        data = self.frames[index][1]
        ctypes.memmove(self.bits, data.tobytes(), data.nbytes)
        self._paint(self.x, self.y)

    def _check_control(self):
        """Host / 侧栏面板通过 control.json 遥控：显示、隐藏、静音、归位。"""
        try:
            stamp = os.path.getmtime(CONTROL_PATH)
        except OSError:
            return
        if stamp == self.control_mtime:
            return
        self.control_mtime = stamp
        try:
            with open(CONTROL_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return
        seq = int(data.get("seq") or 0)
        if seq <= self.control_seq:
            return
        self.control_seq = seq

        if "visible" in data:
            want = bool(data["visible"])
            if want != self.visible:
                self.visible = want
                user32.ShowWindow(self.hwnd, 8 if want else SW_HIDE)
                if not want:
                    user32.ShowWindow(self.bubble.hwnd, SW_HIDE)
                    self.bubble.visible = False
        if "muted" in data:
            self.muted = bool(data["muted"])
            self._save_pos()
            if self.muted:
                user32.ShowWindow(self.bubble.hwnd, SW_HIDE)
                self.bubble.visible = False
        if data.get("center"):
            self.x = self.right - self.w - 30
            self.y = self.bottom - self.h - 10
            self._paint(self.x, self.y)
            self._save_pos()

    def _probe_foreground(self):
        """每秒把前台窗口标题写出去。Host 靠它判断「他停在哪个页面」。

        让桌宠干这活而不是 Host：它本来就在 Win32 里，GetForegroundWindow 一行事；
        Host 是 Node，拿这个得再起个子进程，不值。
        """
        now = time.time()
        if now - self.probe_at < 1.0:
            return
        self.probe_at = now
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd or hwnd == self.hwnd:
                return
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value.strip()
        except Exception:
            return

        # 换了窗口或标题变了，就叫后台线程去读一次地址栏（B站特化要用 BV 号）
        if hwnd != getattr(self, "_probed_hwnd", None) or title != getattr(self, "_probed_title", None):
            self._probed_hwnd = hwnd
            self._probed_title = title
            self.current_url = ""
            self.url_wanted = True

        payload = {"hwnd": int(hwnd), "title": title, "at": int(now * 1000)}
        url = self.current_url
        if url:
            payload["url"] = url
            match = re.search(r"/video/(BV[0-9A-Za-z]{10})", url)
            if match:
                payload["bv"] = match.group(1)
        try:
            # 原子写：Host 每 2 秒读一次，直接覆盖写会让它读到半截 JSON
            # （readJson 返回 null，然后那一边就以为「人走了」——踩过）
            tmp = FOREGROUND_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                # 把 hwnd 也写出去：标题会变（记事本加 *、页面标题刷新），
                # 但同一个窗口的 hwnd 不变。Host 靠 hwnd 判断「他还在同一处」。
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(tmp, FOREGROUND_PATH)
        except Exception:
            pass

    def _tick(self):
        # 整轮包起来。以前任何一步抛异常都会被 ctypes 静默吞掉，然后这一轮剩下的
        # 全跳过（气泡没了、眨眼停一拍），而且没有任何记录 —— 查都无从查起。
        try:
            self._check_say()
            self._check_control()
            self._probe_foreground()
            self.bubble.tick()
            now = time.time()
            if self.blink_until:
                if now >= self.blink_until:
                    self._set_frame(0)
                    self.blink_until = 0.0
                    self.next_blink = now + random.uniform(2.5, 6.5)
            elif now >= self.next_blink:
                self._set_frame(1)
                self.blink_until = now + random.uniform(0.10, 0.16)
        except Exception:
            self._log("tick 抛异常:\n" + traceback.format_exc()[-1200:])

    def _paint(self, x, y):
        pt_dst = POINT(x, y)
        pt_src = POINT(0, 0)
        sz = SIZE(self.w, self.h)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(
            self.hwnd, self.hdc_screen, ctypes.byref(pt_dst), ctypes.byref(sz),
            self.hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), ULW_ALPHA)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TIMER:
            self._tick()
            return 0
        if msg == WM_LBUTTONDOWN:
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            self._drag = (pt.x, pt.y, self.x, self.y)
            user32.SetCapture(hwnd)      # 不抓的话，指针一离开窗口就收不到 MOUSEMOVE
            return 0
        if msg == WM_MOUSEMOVE and self._drag is not None:
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            nx = self._drag[2] + (pt.x - self._drag[0])
            ny = self._drag[3] + (pt.y - self._drag[1])
            nx = max(self.left, min(nx, self.right - self.w))
            ny = max(self.top, min(ny, self.bottom - self.h))
            self.x, self.y = nx, ny
            self._paint(nx, ny)
            if self.bubble.visible:              # 气泡跟着走，别把人甩在半路
                bx, by = self._bubble_pos(self.bubble.w, self.bubble.h)
                self.bubble.move_to(bx, by)
            return 0
        if msg == WM_LBUTTONUP:
            user32.ReleaseCapture()
            self._drag = None
            self._save_pos()
            return 0
        if msg == WM_RBUTTONUP:
            self._show_menu()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _save_pos(self):
        self.state["x"] = self.x
        self.state["y"] = self.y
        self.state["muted"] = bool(self.muted)
        save_state(self.state)

    def _ask(self):
        """弹一个单行输入框问她一句。

        单开一个进程跑 tkinter：这边是 Win32 消息循环，两套循环塞一个进程会互相卡。
        分了进程，输入框崩了也不连累桌宠。问题由那边写进 ask.json，Host 500ms 接走。
        """
        script = os.path.join(HERE, "ask_box.py")
        if not os.path.exists(script):
            return
        try:
            subprocess.Popen(
                [sys.executable, script, STATE_DIR],
                cwd=HERE,
                close_fds=True,
                creationflags=0x08000000,   # CREATE_NO_WINDOW：别闪黑框
            )
        except Exception:
            pass

    def _show_menu(self):
        """右键菜单：问她一句 / 归位 / 暂停说话 / 退出。"""
        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(hmenu, MF_STRING, 4, "问她一句")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, 1, "归位")
        user32.AppendMenuW(hmenu, MF_STRING, 2, "恢复说话" if self.muted else "暂停说话")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, 3, "退出")
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        prev = user32.GetForegroundWindow()
        user32.SetForegroundWindow(self.hwnd)     # 不先抢一下，菜单点外面关不掉
        cmd = user32.TrackPopupMenu(
            hmenu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(hmenu)
        if cmd == 4:
            self._ask()
            try:
                if prev and prev != self.hwnd:
                    user32.SetForegroundWindow(prev)
            except Exception:
                pass
        elif cmd == 1:
            self.x = self.right - self.w - 30
            self.y = self.bottom - self.h - 10
            self._paint(self.x, self.y)
            self._save_pos()
        elif cmd == 2:
            self.muted = not self.muted
            self._save_pos()
            if self.muted:
                user32.ShowWindow(self.bubble.hwnd, SW_HIDE)
                self.bubble.visible = False
        elif cmd == 3:
            user32.PostQuitMessage(0)
        else:
            try:
                if prev and prev != self.hwnd:
                    user32.SetForegroundWindow(prev)
            except Exception:
                pass

    def run(self):
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    if not claim_instance():
        return
    Pet(os.path.join(ASSETS, "open_rgba.png"),
        os.path.join(ASSETS, "closed_rgba.png")).run()


if __name__ == "__main__":
    main()
