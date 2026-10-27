"""让 Clawd 写日记。

用法：
  python3 write_diary.py               # 写今天（凌晨 4 点前算前一天）
  python3 write_diary.py 2026-10-19    # 写指定日期
  python3 write_diary.py --catchup 7   # 补写最近 7 天里还没写的（不含今天；电脑合盖错过了也不怕）
  python3 write_diary.py --rebuild     # 只重新生成网页数据
加 --force 会覆盖已经写过的那天。
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys

from extract import GEN_MARKER, diary_day, extract

ROOT = os.path.dirname(os.path.abspath(__file__))
ENTRIES = os.path.join(ROOT, "entries")
PERSONA = os.path.join(ROOT, "persona.md")
DATA_JS = os.path.join(ROOT, "web", "data.js")
MEMORY_DAYS = 5
MODEL = "sonnet"  # 写日记用的模型：haiku / sonnet / opus
WEEKDAYS = "一二三四五六日"
MOODS = {"happy", "love", "worried", "sleepy", "proud"}
WEATHERS = {"晴", "多云", "小雨", "雷阵雨", "彩虹", "星星"}

PROMPT = """{marker}
你现在不是编程助手，而是在扮演一个角色写私密日记。不要调用任何工具，直接输出结果。

# 你的人设
{persona}

# 你最近几天写过的日记（保持连续性）
{memory}

# 今天的基本情况
日期：{date}（周{weekday}）
宝宝第一次来找你：{first}，最后一次：{last}{late}
今天一起待了大约 {minutes} 分钟，来回聊了 {sessions} 段，宝宝发了 {messages} 条消息
在哪儿聊的：{sources}
涉及的项目：{projects}

# 今天的聊天记录（「我」是宝宝，「CC」是你）
{material}

# 输出
只输出一个 JSON 对象，不要代码块，不要任何其他文字：
{{
  "title": "这篇日记的标题，不超过 12 个字，要有人味儿",
  "weather": "宝宝今天的心情天气，只能是：晴/多云/小雨/雷阵雨/彩虹/星星",
  "mood": "你写完日记时自己的表情，只能是：happy/love/worried/sleepy/proud",
  "body": "日记正文，180 到 300 字，用 \\n 分 2 到 4 段；引用别人说的话用中文双引号 “”，不要用「」",
  "ps": "P.S. 后面的悄悄话，不超过 40 字，不用写 P.S.",
  "sticky": "贴在页边的便利贴，不超过 18 字，比如一句叮嘱",
  "doodle": "你给今天画的小涂鸦的配字，不超过 10 字"
}}
"""


QUOTES = str.maketrans({"「": "“", "」": "”", "『": "“", "』": "”"})


def normalize_quotes(text):
    """直角引号看着 AI 味重，统一换成 “”。"""
    return text.translate(QUOTES)


def load_entry(day):
    path = os.path.join(ENTRIES, f"{day}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def recent_memory(day):
    notes = []
    for i in range(MEMORY_DAYS, 0, -1):
        e = load_entry(day - dt.timedelta(days=i))
        if e:
            notes.append(f"【{e['date']}｜{e['title']}】\n{e['body']}\nP.S. {e['ps']}")
    return "\n\n".join(notes) or "（这是第一篇日记）"


def ask_claude(prompt):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_") and k != "CLAUDECODE"}
    out = subprocess.run(
        ["claude", "-p", "--model", MODEL, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=600, env=env, cwd=ROOT,
    )
    if out.returncode != 0:
        raise RuntimeError(f"claude 调用失败：{out.stderr.strip() or out.stdout.strip()}")
    match = re.search(r"\{.*\}", out.stdout, re.S)
    if not match:
        raise RuntimeError(f"没拿到 JSON：{out.stdout[:300]}")
    return json.loads(match.group(0))


def write_day(day, force=False):
    today = diary_day(dt.datetime.now().astimezone())
    old = load_entry(day)
    # 当天还没过完时写的是草稿，等这天过去再重写一遍
    if old and not force and not (old.get("draft") and day < today):
        print(f"{day} 已经写过了")
        return False
    data = extract(day)
    if not data:
        print(f"{day} 宝宝没来找我")
        return False
    s = data["stats"]
    prompt = PROMPT.format(
        marker=GEN_MARKER,
        persona=open(PERSONA).read(),
        memory=recent_memory(day),
        date=day.isoformat(),
        weekday=WEEKDAYS[day.weekday()],
        first=s["first"],
        last=s["last"],
        late="（熬夜了）" if s["late_night"] else "",
        minutes=s["active_minutes"],
        sessions=s["sessions"],
        messages=s["messages"],
        sources="、".join(f"{k} {v} 段" for k, v in s["sources"].items()),
        projects="、".join(s["projects"]),
        material=data["material"],
    )
    print(f"{day} 正在写……（素材 {len(data['material'])} 字）")
    entry = ask_claude(prompt)
    for key in ("title", "body", "ps", "sticky", "doodle"):
        entry[key] = normalize_quotes(entry.get(key, ""))
    entry["mood"] = entry.get("mood") if entry.get("mood") in MOODS else "happy"
    entry["weather"] = entry.get("weather") if entry.get("weather") in WEATHERS else "晴"
    entry.update(date=day.isoformat(), weekday=WEEKDAYS[day.weekday()], stats=s, draft=day >= today,
                 written_at=dt.datetime.now().astimezone().isoformat(timespec="minutes"))
    os.makedirs(ENTRIES, exist_ok=True)
    with open(os.path.join(ENTRIES, f"{day}.json"), "w") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    print(f"{day} 写好了：《{entry['title']}》")
    return True


def rebuild():
    entries = []
    if os.path.isdir(ENTRIES):
        for name in sorted(os.listdir(ENTRIES)):
            if name.endswith(".json"):
                with open(os.path.join(ENTRIES, name)) as f:
                    entries.append(json.load(f))
    os.makedirs(os.path.dirname(DATA_JS), exist_ok=True)
    with open(DATA_JS, "w") as f:
        f.write("window.DIARY = " + json.dumps(entries, ensure_ascii=False, indent=1) + ";\n")
    print(f"网页数据已更新：{len(entries)} 篇")


def main(argv):
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    today = diary_day(dt.datetime.now().astimezone())
    if argv[:1] == ["--rebuild"]:
        pass
    elif argv[:1] == ["--catchup"]:
        n = int(argv[1]) if len(argv) > 1 else 7
        for i in range(n, 0, -1):  # 只补已经过完的日子
            try:
                write_day(today - dt.timedelta(days=i), force)
            except Exception as e:  # 某天失败不影响其他天
                print(f"{today - dt.timedelta(days=i)} 失败：{e}")
    else:
        write_day(dt.date.fromisoformat(argv[0]) if argv else today, force)
    rebuild()


if __name__ == "__main__":
    main(sys.argv[1:])
