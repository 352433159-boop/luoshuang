#!/usr/bin/env python3
"""相关新闻关键词预警：抓取东财新闻，匹配关键词后推送微信。"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = Path(os.environ.get("NEWS_STATE", REPO_ROOT / "news_state.json"))

KEYWORDS = [
    ("OpenAI", "AI/OpenAI", "AI叙事与科技板块情绪"),
    ("半导体", "半导体", "国产替代+AI芯片景气"),
    ("芯片", "芯片", "半导体景气与政策"),
    ("电网", "电网", "电网投资与特高压订单"),
    ("特高压", "特高压", "电网设备催化"),
    ("黄金", "黄金", "避险+央行购金"),
    ("降息", "美联储/降息", "利率与估值"),
    ("创新药", "创新药", "出海BD+医保政策"),
    ("机器人", "机器人", "AI应用主题"),
    ("稀土", "稀土", "供给收缩与价格"),
    ("光伏", "光伏", "产能与价格出清"),
    ("数据中心", "算力", "AI算力需求"),
    ("港股", "港股", "估值与流动性"),
    ("券商", "券商", "成交放大与市场情绪"),
    ("有色金属", "有色", "铜金供需与价格"),
    ("消费", "消费", "政策与复苏"),
    ("恒生科技", "港股科技", "港股流动性修复"),
    ("银行", "银行", "高股息与息差"),
    ("红利", "红利", "防守资金流向"),
    ("AI安全", "AI安全", "AI安全新方向"),
    ("网络安全", "网络安全", "AI安全需求"),
]


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def search_news(keyword):
    param = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": 1,
                "pageSize": 8,
                "preTag": "",
                "postTag": "",
            }
        },
    }
    url = (
        "https://search-api-web.eastmoney.com/search/jsonp?cb=cb&param="
        + urllib.parse.quote(json.dumps(param, ensure_ascii=False))
    )
    try:
        text = http_get(url)
        data = json.loads(text[text.find("(") + 1 : text.rfind(")")])
        return data.get("result", {}).get("cmsArticleWebOld", [])
    except Exception:
        return []


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"seen": [], "last_push": 0}


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
    seen = set(state.get("seen", []))
    now = datetime.now(TZ)
    hits = []

    for keyword, label, logic in KEYWORDS:
        for art in search_news(keyword):
            title = art.get("title", "")
            url = art.get("url", "")
            date_str = art.get("date", "")
            if not title or not url:
                continue
            try:
                pub = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=TZ
                )
            except Exception:
                continue
            if (now - pub).total_seconds() > 45 * 60:
                continue
            key = url
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                f"📰 <b>{label}</b>：{title}<br>"
                f"<span style='color:#555;font-size:13px;'>{pub.strftime('%H:%M')}｜逻辑：{logic}</span>"
            )

    now_ts = time.time()
    if hits and (now_ts - state.get("last_push", 0)) >= 300:
        html = (
            "<div style='font-size:16px;line-height:1.7;color:#000;'>"
            "<b>📰 相关新闻提醒</b><br>" + "<br>".join(hits[:10])
            + "<br><br><span style='color:#555;font-size:13px;'>关键词规则匹配，非AI分析。不构成投资建议。</span></div>"
        )
        state["last_push"] = now_ts
        state["seen"] = list(seen)[-200:]
        save_state(state)
        return push("📰 相关新闻提醒", html)

    state["seen"] = list(seen)[-200:]
    save_state(state)
    print("NO_NEWS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
