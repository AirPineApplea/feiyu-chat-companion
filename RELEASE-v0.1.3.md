# 肥鱼陪聊 v0.1.3

一个小修正，但它改的是一个「说了没做到」的问题。

---

## 改了什么

**「看什么」这一组，现在只有装了「刷B站」插件才显示。**

0.1.2 里，所有人都会看到「只看标题 / 标题 + B站内容」这两个按钮。但读字幕、翻评论靠的是 **`dsh-bili-scroll`（刷B站）** 注册的 `bili_subtitle` / `bili_comments` 工具——**本插件自己一个 B站 工具都没有。**

没装那个插件的人选了「标题 + B站内容」，什么都不会发生：多读了一次地址栏，多带了一个 BV 号，模型手里却没有能查的东西。开关是真的，效果是假的。

现在：

- **没装**：「看什么」整组不渲染（不是灰按钮），Host 也不再把 BV 号塞进给她的话里
- **装了**：才有那一档，说明文字改成「我会用**「刷B站」插件的工具**去翻字幕和评论」，把依赖摆明

探测方式是问 DSH 的工具表里有没有 `bili_subtitle`——「能不能读到内容」本来就等于「工具在不在」，不去猜包名。

## 想读内容？另装一个

```powershell
dsh plugin --profile desktop add github:c1overzz/dsh-bili-scroll
```

再把 `uiautomation` 装上（读地址栏、抠 BV 号要用），用 DSH 自带的那份 Python：

```powershell
& "C:\Users\<你>\AppData\Local\Programs\DeepSeek Harness\resources\runtime\primary-runtime\dependencies\python\python.exe" -m pip install uiautomation
```

只装「刷B站」不装 `uiautomation`，她有工具但拿不到 BV 号，还是只能凭标题说话。

## 文档

README 补了 `### 刷B站（dsh-bili-scroll）` 一节，跟「肥鱼日记」「语音」两个联动并列，写清了三件事：装了什么效果、怎么探测、没装会怎样。

---

## 升级

```powershell
dsh plugin --profile desktop add github:AirPineApplea/feiyu-chat-companion
```

装完**重启 DSH**，再刷新一下网页。

## 许可

MIT
