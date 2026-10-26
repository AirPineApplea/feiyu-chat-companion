# 投稿 PR 正文（可直接粘贴）

发 PR 到 `awesome-dsh-plugin/awesome-dsh-plugin`，只加一个文件：

```
data/plugins/AirPineApplea__feiyu-chat-companion.yml
```

内容就是仓库根目录 `上架投稿.yml` 去掉开头注释后剩下的部分。

---

## PR 标题

```
Add AirPineApplea/feiyu-chat-companion (ui)
```

## PR 正文

```markdown
## What / 加什么

`AirPineApplea/feiyu-chat-companion` — 给 DeepSeek Harness 的桌面桌宠，分类 `ui`。

一个文件：`data/plugins/AirPineApplea__feiyu-chat-companion.yml`。

## 它是什么

桌宠不是嵌在应用里的网页元素，而是一个真正的 Win32 分层窗口（`UpdateLayeredWindow`，逐像素 alpha）：置顶、不进任务栏、不抢焦点、能拖、撞到屏幕边缘贴住、随机眨眼、头顶弹气泡说话。右键菜单里有一项「问她一句」，弹一个单行输入框，答案回到气泡里。

它是独立的 Python overlay 进程 + DSH Host 半边：Host 负责拉起进程、判「你在同一窗口停够 10 秒」、把话写进 `say.json`；桌宠每 60ms 看一眼 mtime，变了就播。两边解耦，所以别的插件也能往 `say.json` 写一句话让它开口。

## 分类为什么是 ui

它的产出是一个界面元素（桌面窗口 + 侧栏面板），不是工具集、不是会话改动、也不属于主题。同类里终端/TUI 类的条目大多在 `ui`。

## 自查

- [x] `package.json` 声明了 `dsh.bundle`（`{"bundle": {"patch": "./cordis.patch.yml"}, "client": {"platform": "web"}}`），仓库根有 `cordis.patch.yml`
- [x] 仓库已加 `dsh-plugin` topic
- [x] 描述只说功能，不含营销词
- [x] 只加一个文件，没有改动其他条目
- [x] 只跑 Windows（README 已写明），没有吹跨平台

## 平台

Windows 10/11。用了 Win32 layered window，别的平台跑不了——README 和描述里都写清楚了。

## 依赖

零运行时依赖，无构建步骤。Python 用 DSH 自带的那份。可选的 `uiautomation`（读 B站 视频页的地址栏）要用户自己装，不装只是读不到 BV 号，桌宠照常跑。
```

---

## 提交前的两个硬门槛

1. **仓库要存在满 1 天** —— CI 自动检查，我们是今天建的，明天才够。
2. 上游是 `contributing.md`（小写，在根目录），不是我一开始猜的 `CONTRIBUTING.md`。

## 可选但值得加

- **图标**：条目里加 `icon:`，指向 GitHub 托管的位图（png/jpg/webp，约 96px 显示，方形最好）。不写就回退到你的 GitHub 头像。
- **截图**：在**自己仓库**根放 `screenshots.json`（`["assets/xxx.png"]`，1-8 张），市场详情页会按这个顺序展示；不声明则从 README 抽图。
