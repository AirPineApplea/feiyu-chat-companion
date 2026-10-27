# -*- coding: utf-8 -*-
"""探针：直接拉起桌宠，看它能不能活下来、pid 有没有重写。

不写死任何用户名：路径全从环境变量推，别人拿去也能跑。
结果写文件而不是 stdio —— 沙箱里子进程的管道可能被拒（spawn EPERM）。
"""
import os
import subprocess
import sys
import tempfile
import time

LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.join(
    os.path.expanduser("~"), "AppData", "Local"
)
DSH_HOME = os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")

PYW = os.path.join(
    LOCALAPPDATA,
    "Programs",
    "DeepSeek Harness",
    "resources",
    "runtime",
    "primary-runtime",
    "dependencies",
    "python",
    "pythonw.exe",
)
SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "overlay", "pet_win32.py"
)
PIDFILE = os.path.join(DSH_HOME, "storages", "feiyu-chat", "pet.pid")
OUT = os.path.join(tempfile.gettempdir(), "pet_spawn_probe.txt")

if not os.path.exists(PYW):
    sys.exit("找不到 pythonw：%s" % PYW)


def main():
    lines = []
    p = subprocess.Popen([PYW, SCRIPT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lines.append("spawn ok pid=%d" % p.pid)
    time.sleep(5)
    rc = p.poll()
    lines.append("5 秒后 poll=%r" % (rc,))
    try:
        with open(PIDFILE, "r", encoding="utf-8") as fh:
            lines.append("pet.pid = %s (期望 %d)" % (fh.read().strip(), p.pid))
    except Exception as exc:
        lines.append("读 pid 失败: %r" % (exc,))
    if rc is None:
        p.terminate()
        lines.append("还活着 -> 已 terminate")
    else:
        lines.append("已经退出，退出码 %r（如果她本来就在跑，这是单实例检查在拦）" % (rc,))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
