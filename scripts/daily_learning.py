#!/usr/bin/env python3
"""📚 每日学习计划"""

import os, requests
from datetime import datetime, timezone, timedelta
from learning_data import get_content, LABELS

TZ = timezone(timedelta(hours=8))
DAY = datetime.now(TZ)
DOY = DAY.timetuple().tm_yday
CATS = ["english", "programming", "investing", "reading",
        "general", "writing", "psychology", "math"]


def build():
    now = DAY.strftime("%Y年%m月%d日 %A")
    L = [f"📚 每日学习 · {now}", chr(9472)*20]

    for cat in CATS:
        label, _ = LABELS[cat]
        e = get_content(cat, DOY)
        L.append(f"\n{label}")

        if cat == "english":
            word, pron, en, zh = e
            en_short = en[:60] + chr(8230) if len(en) > 60 else en
            L.append(f"  {word} {pron}")
            L.append(f"  {zh} | {en_short}")
        elif cat == "reading":
            book, quote = e
            q_short = quote[:60] + chr(8230) if len(quote) > 60 else quote
            L.append(f"  {book}")
            L.append(f"  {q_short}")
        elif cat == "general":
            name, desc = e
            L.append(f"  {name}: {desc[:100]}")
        elif cat == "writing":
            t, tip = e
            L.append(f"  {t}: {tip[:100]}")
        else:
            n, d = e
            L.append(f"  {n}: {d[:100]}")

    L.extend([f"\n{chr(9472)*20}", "每天进步一点点 🤖 GH Actions"])

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
        json={"token": token, "title": title, "content": content, "template": "txt"},
        timeout=15).json()
    print("OK" if r.get("code") == 200 else f"FAIL: {r}")


if __name__ == "__main__":
    print("Generating...\n")
    rpt = build()
    print(f"Len: {len(rpt)}")
    print(rpt)
    push("📚 每日学习计划", rpt)
