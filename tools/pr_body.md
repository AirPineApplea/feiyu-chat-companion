## What / 加什么

`AirPineApplea/feiyu-chat-companion` — 给 DeepSeek Harness 的桌面桌宠，分类 `ui`。

一个文件：`data/plugins/AirPineApplea__feiyu-chat-companion.yml`。

## 它是什么

桌宠不是嵌在应用里的网页元素，而是一个真正的 Win32 分层窗口（`UpdateLayeredWindow`，逐像素 alpha）：置顶、不进任务栏、不抢焦点、能拖、撞到屏幕边缘贴住、随机眨眼、头顶弹气泡说话。右键菜单里有一项「问她一句」，弹一个单行输入框，答案回到气泡里。

独立的 Python overlay 进程 + DSH Host 半边：Host 负责拉起进程、判断「你在同一窗口停够 10 秒」、把话写进 `say.json`；桌宠每 60ms 看一眼 mtime，变了就播。两边靠文件解耦。

## 分类为什么是 ui

产出是一个界面元素（桌面窗口 + 侧栏面板），不是工具集、不是会话改动、也不是主题。

## 自查

- [x] `package.json` 声明了 `dsh.bundle`，仓库根有 `cordis.patch.yml`
- [x] 仓库已加 `dsh-plugin` topic
- [x] 已发布 npm：`feiyu-chat-companion@0.1.8`，`repository` 指回本仓库
- [x] 描述只说功能，不含营销词；描述里的 10 秒、右键输入框、分层窗口都能在代码里对上
- [x] 只加一个文件，没有改动其他条目

## 平台

Windows 10/11。用了 Win32 layered window，别的平台跑不了，README 与条目描述里都写明了。

## 依赖

零运行时依赖、无构建步骤。Python 用 DSH 自带的那份；可选的 `uiautomation`（读 B站 视频页地址栏取 BV 号）要用户自己装，不装只是读不到 BV 号，桌宠照常跑。
