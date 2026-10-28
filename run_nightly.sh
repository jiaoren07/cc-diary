#!/bin/zsh
# 每天凌晨由 launchd 调用：补写最近 3 天里还没写完的日记（电脑睡着错过了，醒来会补跑）
# 加 --check 只测试后台能不能连上 Claude，不写日记
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/bin:/bin"
cd "$(dirname "$0")"
mkdir -p logs

# 后台任务不会自动走系统代理。需要代理的话，在 local.env 里写一行：
#   DIARY_PROXY=http://127.0.0.1:7890
# 代理软件没开时自动直连，不会因为代理没开而失败
[[ -f local.env ]] && source local.env
if [[ -n "$DIARY_PROXY" ]] && nc -z ${${DIARY_PROXY##*://}%:*} ${DIARY_PROXY##*:} 2>/dev/null; then
  export HTTPS_PROXY="$DIARY_PROXY" HTTP_PROXY="$DIARY_PROXY"
fi

if [[ "$1" == "--check" ]]; then
  echo "===== 连接测试 $(date '+%F %T') 代理：${HTTPS_PROXY:-直连} =====" >> logs/nightly.log
  echo "[[CC-DIARY-GEN]] 只回复两个字：收到" | claude -p --model sonnet --output-format text >> logs/nightly.log 2>&1
  echo "exit=$?" >> logs/nightly.log
  exit
fi

echo "===== $(date '+%F %T') 代理：${HTTPS_PROXY:-直连} =====" >> logs/nightly.log
python3 write_diary.py --catchup 3 >> logs/nightly.log 2>&1
