#!/usr/bin/env python3
"""📚 每日学习计划 — 含今日行动"""
import os, requests
from datetime import datetime, timezone, timedelta
from learning_data import get_content, LABELS

TZ = timezone(timedelta(hours=8))
DAY = datetime.now(TZ)
DOY = DAY.timetuple().tm_yday
CATS = ["english", "programming", "investing", "reading", "general",
        "writing", "psychology", "math", "hairstylist", "shopowner"]


def today_task(cat, e):
    """为每个科目生成今日行动任务"""
    tasks = {
        "english":     lambda: f"  👉 今日任务: 用'{e[0]}'造3个句子，写在备忘录里 💪",
        "programming": lambda: f"  👉 今日任务: 今天写代码时留意一下'{e[0]}'相关的场景 💻",
        "investing":   lambda: f"  👉 今日任务: 用'{e[0]}'的视角分析你的自选股 📊",
        "reading":     lambda: f"  👉 今日任务: 把这段话抄下来，晚上回顾一遍 📝",
        "general":     lambda: f"  👉 今日任务: 观察生活中有没有'{e[0]}'的例子 🔍",
        "writing":     lambda: f"  👉 今日任务: 今天写东西时用上'{e[0]}'的技巧 ✍️",
        "psychology":  lambda: f"  👉 今日任务: 留意今天有没有出现'{e[0]}' 🧐",
        "math":        lambda: f"  👉 今日任务: 用这个知识算一笔你身边的实际数字 🧮",
        "hairstylist": lambda: f"  👉 今日任务: 服务下一位客户时试试'{e[0]}' ✂️",
        "shopowner":   lambda: f"  👉 今日任务: 今天花5分钟做这件事: {e[0]} 🏪",
    }
    return tasks.get(cat, lambda: "")()


def build():
    now = DAY.strftime("%Y年%m月%d日 %A")
    L = [f"📚 每日学习 · {now}", chr(9472)*22]

    for cat in CATS:
        label, _ = LABELS[cat]
        e = get_content(cat, DOY)
        L.append(f"\n{label}")

        if cat == "english":
            w, pron, meaning, etymology, usage, en, zh, tip = e
            L.append(f"  {w} {pron}")
            L.append(f"  {meaning}")
            L.append(f"  📖 {etymology[:60]}…" if len(etymology)>60 else f"  📖 {etymology}")
            L.append(f"  💬 {en}")
            L.append(f"  {zh}")

        elif cat == "reading":
            book, quote = e
            q2 = quote[:60] + chr(8230) if len(quote) > 60 else quote
            L.append(f"  {book}")
            L.append(f"  {q2}")

        elif cat in ("hairstylist", "shopowner"):
            topic, tip = e
            L.append(f"  {topic}")
            L.append(f"  {tip[:100]}…" if len(tip)>100 else f"  {tip}")

        else:
            n, d = e
            L.append(f"  {n}")
            show = d[:100] + chr(8230) if len(d) > 100 else d
            L.append(f"  {show}")

        L.append(today_task(cat, e))

    L.extend([f"\n{chr(9472)*22}", "每天进步一点点 🤖 看完就去练！"])

    full = "\n".join(L)
    if len(full) > 1900:
        lines = full.split("\n")
        keep = []
        for line in lines:
            if len("\n".join(keep + [line])) > 1850:
                keep.append("(内容已截断)")
                break
            keep.append(line)
        full = "\n".join(keep)
    return full


def push(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print(content)
        return
    r = requests.post("https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "txt"}, timeout=15).json()
    print("OK" if r.get("code") == 200 else f"FAIL: {r}")


if __name__ == "__main__":
    print("生成中...\n")
    rpt = build()
    print(f"长度: {len(rpt)} 字\n")
    print(rpt)
    push("📚 今日学习任务清单", rpt)
