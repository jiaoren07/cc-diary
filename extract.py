"""从 ~/.claude/projects 里提取某一天的对话素材（桌面端 + VS Code 插件都在这里）。

一天按凌晨 4 点切分：凌晨 1 点还在聊，算前一天的「熬夜」。
只保留你打的字和 CC 回复里的文字，丢掉工具调用、工具输出、代码块和注入的系统标签。
"""
import datetime as dt
import glob
import json
import os
import re
import sys

PROJECTS = os.path.expanduser("~/.claude/projects")
DAY_CUTOFF_HOUR = 4
GEN_MARKER = "[[CC-DIARY-GEN]]"  # 生成日记时自己发出的 prompt，带这个标记的会话要跳过
MAX_MSG_CHARS = {"user": 500, "assistant": 260}
MAX_TOTAL_CHARS = 45000

SOURCE_NAMES = {"claude-desktop": "桌面端", "claude-vscode": "VS Code", "cli": "终端"}

TAG_BLOCK = re.compile(r"<([a-zA-Z][\w\-]*)(?:\s[^>]*)?>.*?</\1>", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
SECRETS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd)\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def local_time(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()


def diary_day(t):
    return (t - dt.timedelta(hours=DAY_CUTOFF_HOUR)).date()


def clean(text, limit):
    # 注入的系统标签整块删掉；粘贴内容是用户自己的意思，只去掉标签留下正文
    text = TAG_BLOCK.sub(lambda m: m.group(0) if m.group(1) == "pasted_content" else " ", text)
    text = re.sub(r"</?pasted_content[^>]*>", " ", text)
    text = CODE_BLOCK.sub(" [代码] ", text)
    for pat in SECRETS:
        text = pat.sub("[已隐去]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


def message_text(d):
    """返回 (role, 文本)；不是人写的/不是 CC 说的就返回 None。"""
    if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
        return None
    t = d.get("type")
    content = (d.get("message") or {}).get("content")
    if t == "user":
        if (d.get("origin") or {}).get("kind") not in (None, "human"):
            return None
        if isinstance(content, str):
            parts = [content]
        elif isinstance(content, list):
            if any(b.get("type") == "tool_result" for b in content):
                return None
            parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            if any(b.get("type") == "image" for b in content):
                parts.append("[发了一张图]")
        else:
            return None
        text = clean(" ".join(parts), MAX_MSG_CHARS["user"])
        if not text or text.startswith("[Request interrupted"):
            return None
        return "user", text
    if t == "assistant" and isinstance(content, list):
        parts = [b.get("text", "") for b in content if b.get("type") == "text"]
        text = clean(" ".join(parts), MAX_MSG_CHARS["assistant"])
        return ("assistant", text) if text else None
    return None


def load_sessions(day):
    sessions = []
    for path in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")):
        if dt.date.fromtimestamp(os.path.getmtime(path)) < day:
            continue  # 文件最后改动早于这一天，不可能有这天的消息
        msgs, entry, cwd, title, skip = [], None, None, None, False
        with open(path, errors="ignore") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "ai-title":
                    title = d.get("aiTitle") or d.get("title") or title
                ts = d.get("timestamp")
                if not ts:
                    continue
                t = local_time(ts)
                if diary_day(t) != day:
                    continue
                got = message_text(d)
                if not got:
                    continue
                if GEN_MARKER in got[1]:
                    skip = True
                    break
                entry = entry or d.get("entrypoint")
                cwd = cwd or d.get("cwd")
                msgs.append((t, got[0], got[1]))
        if skip or not any(r == "user" for _, r, _ in msgs):
            continue
        msgs.sort(key=lambda m: m[0])
        sessions.append({
            "source": SOURCE_NAMES.get(entry, entry or "未知"),
            "project": os.path.basename(cwd or "") or "~",
            "title": title,
            "start": msgs[0][0],
            "end": msgs[-1][0],
            "msgs": msgs,
        })
    sessions.sort(key=lambda s: s["start"])
    return sessions


def stats(sessions):
    user_times = [t for s in sessions for t, r, _ in s["msgs"] if r == "user"]
    sources = {}
    for s in sessions:
        sources[s["source"]] = sources.get(s["source"], 0) + 1
    projects = []
    for s in sessions:
        if s["project"] not in projects:
            projects.append(s["project"])
    first, last = min(user_times), max(user_times)
    active_min = sum(max(1, (s["end"] - s["start"]).total_seconds() // 60) for s in sessions)
    return {
        "sessions": len(sessions),
        "messages": len(user_times),
        "first": first.strftime("%H:%M"),
        "last": last.strftime("%H:%M"),
        "late_night": last.hour < DAY_CUTOFF_HOUR or last.hour >= 23,
        "active_minutes": int(active_min),
        "projects": projects,
        "sources": sources,
    }


def render(sessions, budget=MAX_TOTAL_CHARS):
    def build(assistant_limit):
        out = []
        for i, s in enumerate(sessions, 1):
            head = f"## 会话{i}｜{s['source']}｜项目 {s['project']}｜{s['start']:%H:%M}-{s['end']:%H:%M}"
            if s["title"]:
                head += f"｜标题：{s['title']}"
            out.append(head)
            for t, role, text in s["msgs"]:
                if role == "assistant":
                    if assistant_limit == 0:
                        continue
                    text = text[:assistant_limit]
                out.append(f"[{t:%H:%M}] {'我' if role == 'user' else 'CC'}：{text}")
        return "\n".join(out)

    for limit in (260, 120, 0):
        text = build(limit)
        if len(text) <= budget:
            return text
    return text[:budget] + "\n…（太长，后面截掉了）"


def extract(day):
    sessions = load_sessions(day)
    if not sessions:
        return None
    return {"date": day.isoformat(), "stats": stats(sessions), "material": render(sessions)}


if __name__ == "__main__":
    day = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else diary_day(dt.datetime.now().astimezone())
    result = extract(day)
    if not result:
        print(f"{day} 没有对话")
        sys.exit(0)
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
    print(result["material"])
