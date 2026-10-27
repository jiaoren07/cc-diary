---
name: diary
description: 打开 Clawd 日记本（Claude Code 自动写的人设日记）。用户输入 /diary，或说「打开日记本」「看看日记」时使用；参数里带「写今天」时先写今天的日记，带「补写」时先补写最近几天的。
---

# 打开 Clawd 日记本

日记本项目目录：`{{DIARY_DIR}}`

## 1. 需要的话先写日记

- 参数里有「写今天」或「写」：运行 `python3 "{{DIARY_DIR}}/write_diary.py"`，告诉用户大约要一分钟。
- 参数里有「补写」：运行 `python3 "{{DIARY_DIR}}/write_diary.py" --catchup 7`。
- 没有参数：跳过这一步。

## 2. 确保本地服务在跑

先检查端口：`lsof -nP -iTCP:8765 -sTCP:LISTEN`。
没有在监听，就在后台启动（只绑定本机地址，局域网里的其他人访问不到）：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory "{{DIARY_DIR}}/web"
```

## 3. 打开日记本

地址：`http://localhost:8765/?open=latest`（直接翻到最新一篇）。

- 在 Claude 桌面端、并且有内置浏览器面板（Claude_Browser 工具）：用 `preview_start` 带上这个 url，在侧边面板里打开。
- 其他情况（VS Code 插件、终端）：运行 `open "http://localhost:8765/?open=latest"` 用系统浏览器打开，并告诉用户：在 VS Code 里也可以按 Cmd+Shift+P → `Simple Browser: Show` → 粘贴这个地址，分屏查看。

## 4. 回复

只回一句话说明日记本已经打开，不要复述日记内容。
