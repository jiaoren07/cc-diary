#!/bin/zsh
# 每天凌晨由 launchd 调用：补写最近 3 天里还没写完的日记（电脑睡着错过了，醒来会补跑）
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/bin:/bin"
cd "$(dirname "$0")"
mkdir -p logs
echo "===== $(date '+%F %T') =====" >> logs/nightly.log
python3 write_diary.py --catchup 3 >> logs/nightly.log 2>&1
