#!/bin/zsh
# 安装 /diary 命令；加 --schedule 会同时装上每天凌晨 4:30 自动写日记的定时任务
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$HOME/.claude/skills/diary"
sed "s#{{DIARY_DIR}}#$DIR#g" "$DIR/skill/SKILL.md" > "$HOME/.claude/skills/diary/SKILL.md"
echo "✓ 已安装 /diary 命令（重开一个 Claude Code 会话后可用）"

if [[ "$1" == "--schedule" ]]; then
  PLIST="$HOME/Library/LaunchAgents/com.clawd.diary.plist"
  mkdir -p "$DIR/logs"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.clawd.diary</string>
  <key>ProgramArguments</key><array><string>$DIR/run_nightly.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err</string>
</dict>
</plist>
PLIST
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  echo "✓ 已安装定时任务：每天 4:30 补写前几天的日记（电脑睡着的话醒来补跑）"
fi
