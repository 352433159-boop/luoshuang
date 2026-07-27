#!/usr/bin/env python3
"""A股日报：采集大盘数据并推送到微信（PushPlus）"""

import os
import json
import requests
import akshare as ak
from datetime import datetime, timezone, timedelta

# === 时区 ===
TZ = timezone(timedelta(hours=8))

# === 1. 获取指数数据 ===
def get_index_data():
    indices = {}
    config = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sz399006", "创业板指"),
    ]
    for symbol, name in config:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            recent = df.tail(2)
            close = float(recent["close"].iloc[-1])
            prev = float(recent["close"].iloc[-2])
            pct = (close - prev) / prev * 100
            indices[name] = (close, pct)
        except Exception as e:
            indices[name] = (None, f"err: {e}")
    return indices

# === 2. 获取板块涨幅榜 ===
def get_sector_rankings(top_n=5):
    try:
        df = ak.stock_board_industry_name_em()
        top5 = df.head(top_n)
        bottom5 = df.tail(top_n)
        return top5, bottom5
    except Exception as e:
        print(f"⚠️  板块数据获取失败: {e}")
        return None, None

# === 3. 格式化日报 ===
def build_message(indices, sector_top, sector_bottom):
    now = datetime.now(TZ).strftime("%Y年%m月%d日 %H:%M")
    lines = [
        f"📊 A股日报 · {now}",
        "━" * 20,
        "",
        "【主要指数】",
    ]
    for name, (price, pct) in indices.items():
        if price is None:
            lines.append(f"  {name}: 获取失败")
        else:
            arrow = "📈" if pct > 0 else "📉" if pct < 0 else "➖"
            lines.append(f"  {name}: {price:.2f}  {arrow} {pct:+.2f}%")

    if sector_top is not None and not sector_top.empty:
        lines.extend(["", "【领涨板块 top5】"])
        for _, r in sector_top.iterrows():
            lines.append(f"  🟢 {r['板块名称']}: {r['涨跌幅']}%")

    if sector_bottom is not None and not sector_bottom.empty:
        lines.extend(["", "【领跌板块 top5】"])
        for _, r in sector_bottom.iterrows():
            lines.append(f"  🔴 {r['板块名称']}: {r['涨跌幅']}%")

    lines.extend([
        "",
        "━" * 20,
        "由 GitHub Actions 自动生成 🤖",
    ])
    return "\n".join(lines)

# === 4. 推送到 PushPlus ===
def push_to_wechat(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print("⚠️  未设置 PUSHPLUS_TOKEN，跳过推送")
        return
    resp = requests.post(
        "https://www.pushplus.plus/send",
        json={
            "token": token,
            "title": title,
            "content": content,
            "template": "txt",
        },
        timeout=15,
    )
    result = resp.json()
    if result.get("code") == 200:
        print("✅ 已推送到微信")
    else:
        print(f"❌ 推送失败: {result}")


if __name__ == "__main__":
    print("🔍 正在采集 A 股数据...")
    indices = get_index_data()
    sector_top, sector_bottom = get_sector_rankings()

    msg = build_message(indices, sector_top, sector_bottom)
    print(msg)
    print()
    push_to_wechat("📊 A股日报", msg)
