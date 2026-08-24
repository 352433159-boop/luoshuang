#!/usr/bin/env python3
"""行情异动实时预警：轮询ETF/指数，触发阈值立即推送微信。"""

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = Path(os.environ.get("ALERT_STATE", REPO_ROOT / "alert_state.json"))

QUOTES = [
    ("sh518880", "黄金", "黄金"),
    ("sh513100", "纳指", "纳指"),
    ("sh512760", "芯片", "半导体"),
    ("sh515790", "光伏", "光伏"),
    ("sh512660", "军工", "军工"),
    ("sh516780", "稀土", "稀土"),
    ("sz159819", "机器人", "机器人"),
    ("sh515180", "红利", "红利"),
    ("sz159338", "A500", "宽基"),
    ("sh515880", "通信", "AI算力"),
    ("sz159938", "医药", "医药"),
    ("sh513050", "中概", "港股"),
    ("sh000001", "上证", "大盘"),
    ("sz399001", "深成", "大盘"),
    ("sz399006", "创业板", "大盘"),
]

LEVELS = {
    "sh512760": [
        (1.08, "below", "芯片ETF跌破1.08，半导体继续规避，不抄底"),
        (1.12, "above", "芯片ETF站回1.12，半导体转震荡，可观察右侧"),
    ],
    "sh515880": [
        (0.68, "above", "通信ETF站稳0.68，AI算力方向可开始分批建仓（007818）"),
    ],
    "sh518880": [
        (9.00, "below", "黄金ETF跌破9.00，若连续3日建议减仓至10%以下"),
    ],
    "sz159938": [
        (0.69, "above", "医药ETF站稳0.69，创新药方向可分批建仓（001344）"),
    ],
}

SUGGESTIONS = {
    "半导体": "半导体急跌/大涨：不追高不抄底；财通006503反弹至7.2-7.4减半或换008887",
    "机器人": "机器人高波动：不追加，等159819站回1.78",
    "黄金": "黄金波动：占比接近15%上限，只持有不加",
    "红利": "红利异动：防守仓，可小额定投",
    "电网": "电网异动：逻辑未坏，回调分批国泰023638",
    "AI算力": "AI算力异动：等515880站稳0.68再分批007818",
    "医药": "医药异动：等159938站稳0.69再分批001344",
    "大盘": "大盘异动：控制仓位，别追高别恐慌割肉",
}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def get_quotes(symbols):
    url = "http://qt.gtimg.cn/q=" + ",".join(symbols)
    text = http_get(url)
    result = {}
    for line in text.splitlines():
        m = re.search(r'v_([a-z0-9]+)="([^"]+)"', line)
        if not m:
            continue
        f = m.group(2).split("~")
        if len(f) < 33:
            continue
        try:
            price = float(f[3])
            chg = float(f[32])
        except ValueError:
            continue
        result[m.group(1)] = {"price": price, "chg": chg}
    return result


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"buckets": {}, "levels": {}, "last_push": 0}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def push(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        print("NO_TOKEN")
        return 2
    payload = json.dumps(
        {"token": token, "title": title, "content": content, "template": "html"}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://www.pushplus.plus/send",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("code") == 200:
            print("PUSH_OK")
            return 0
        print("PUSH_FAIL", json.dumps(result, ensure_ascii=False))
        return 1
    except Exception as exc:
        print("PUSH_ERR", exc)
        return 1


def main():
    state = load_state()
    quotes = get_quotes([s for s, _, _ in QUOTES])
    alerts = []

    for sym, name, sector in QUOTES:
        q = quotes.get(sym)
        if not q:
            continue
        chg = q["chg"]
        price = q["price"]
        bucket = round(chg * 2) / 2  # 0.5% granularity
        if abs(chg) >= 3 and state["buckets"].get(sym) != bucket:
            severe = "font-weight:bold;" if abs(chg) >= 5 else ""
            style = f"color:#e60000;{severe}"
            suggestion = SUGGESTIONS.get(sector, "")
            alerts.append(
                f"<span style='{style}'>🔴 {name} {chg:+.2f}%（现价{price:.3f}）</span>"
                + (f"<br>建议：{suggestion}" if suggestion else "")
            )
            state["buckets"][sym] = bucket

        for level, direction, msg in LEVELS.get(sym, []):
            key = f"{sym}:{level}:{direction}"
            reached = price >= level if direction == "above" else price <= level
            if reached and not state["levels"].get(key):
                alerts.append(f"<span style='color:#e60000;'>⚠️ {msg}</span>")
                state["levels"][key] = True
            if not reached:
                state["levels"][key] = False

    now = time.time()
    if alerts and (now - state.get("last_push", 0)) >= 300:
        html = (
            "<div style='font-size:16px;line-height:1.7;color:#000;'>"
            "<b>⚠️ 基金异动提醒</b><br>" + "<br>".join(alerts)
            + "<br><br><span style='color:#555;font-size:13px;'>自动监控，规则版提醒，不构成投资建议。</span></div>"
        )
        state["last_push"] = now
        save_state(state)
        return push("⚠️ 基金异动提醒", html)

    save_state(state)
    print("NO_ALERT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
