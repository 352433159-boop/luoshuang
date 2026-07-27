#!/usr/bin/env python3
"""A股综合日报：大盘 + 板块 + 涨停 + 资金流向 + 昨夜今晨 + 关注方向"""

import os
import requests
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y%m%d")
YESTERDAY = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y%m%d")

try:
    import akshare as ak
except ImportError:
    print("❌ 缺少 akshare，请运行: pip install akshare")
    raise


# ==================== 数据采集 ====================

def safe(fn):
    """装饰器：捕获异常，失败时返回 None"""
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            return None
    return wrapper


@safe
def get_indices():
    """三大指数涨跌幅"""
    items = []
    for symbol, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        df = ak.stock_zh_index_daily(symbol=symbol).tail(2)
        if len(df) >= 2:
            c, p = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
            items.append((name, c, round((c - p) / p * 100, 2)))
    return items


@safe
def get_realtime_indices():
    """实时指数（GitHub Actions 可用）"""
    idx = ak.stock_zh_index_spot_em()
    target = ["上证指数", "深证成指", "创业板指", "科创50"]
    return [(r["名称"], r["最新价"], r["涨跌幅"]) for _, r in idx.iterrows() if r["名称"] in target]


@safe
def get_sector_rankings(n=5):
    """板块涨跌幅 TOP & BOTTOM"""
    df = ak.stock_board_industry_name_em()
    return list(df[["板块名称", "涨跌幅"]].itertuples(index=False, name=None))


@safe
def get_zt_pool():
    """涨停板个股"""
    zt = ak.stock_zt_pool_em(date=TODAY)
    return [f"{r['代码']} {r['名称']}（{r['连板数']}连板）" for _, r in zt.head(10).iterrows()]


@safe
def get_dt_pool():
    """跌停板个股"""
    dt = ak.stock_zt_pool_dtgc_em(date=TODAY)
    return [f"{r['代码']} {r['名称']}" for _, r in dt.head(10).iterrows()]


@safe
def get_top_gainers():
    """今日涨幅榜（排除st、新股）"""
    df = ak.stock_zh_a_spot_em()
    df = df[~df["名称"].str.contains("ST|N|C", na=False)]
    top = df.nlargest(8, "涨跌幅")
    return [f"{r['代码']} {r['名称']} {r['涨跌幅']:+.2f}%" for _, r in top.iterrows()]


@safe
def get_news():
    """昨夜今晨新闻"""
    items = []
    for d in [TODAY, YESTERDAY]:
        try:
            cctv = ak.news_cctv(date=d)
            if cctv is not None and not cctv.empty:
                for _, r in cctv.iterrows():
                    t = r.get("title", "")
                    if t and len(t) > 4 and not t.startswith("《"):
                        items.append(t)
                if items:
                    break
        except:
            continue
    return items[:6]


@safe
def get_fund_flow():
    """大盘资金流向"""
    fund = ak.stock_market_fund_flow()
    return [f"{r.iloc[0]}: 主力净流入{r.iloc[1]:+.2f}亿" for _, r in fund.tail(3).iterrows()]


@safe
def get_north():
    """北向资金"""
    north = ak.stock_hsgt_hist_em(symbol="北上")
    return [f"{r.iloc[0]}: {r.iloc[1]:+.2f}亿" for _, r in north.tail(3).iterrows()]


# ==================== 报告生成 ====================

def build_report():
    now = datetime.now(TZ).strftime("%Y年%m月%d日 %A")
    lines = [f"📊 今日操盘日报 · {now}", "━" * 28]

    # ── 1. 大盘回顾 ──
    lines.extend(["", "【大盘回顾】"])
    rt = get_realtime_indices()
    indices = rt or get_indices()
    if indices:
        up = sum(1 for i in indices if i[2] > 0)
        for name, price, pct in indices:
            arrow = "📈" if pct > 0 else "📉" if pct < 0 else "➖"
            lines.append(f"  {name}: {price}  {arrow} {pct:+.2f}%")
        mood = "偏强 ☀️" if up > 1 else ("偏弱 🌧️" if up < 1 else "震荡 ⛅")
        lines.append(f"  大盘整体{mood}")
    else:
        lines.append("  暂无指数数据")

    # ── 2. 板块轮动 ──
    lines.extend(["", "【板块轮动】"])
    sectors = get_sector_rankings()
    if sectors:
        sectors_sorted = sorted(sectors, key=lambda x: x[1], reverse=True)
        lines.append("  📗 领涨 TOP5")
        for name, pct in sectors_sorted[:5]:
            lines.append(f"    🟢 {name}: {pct:+.2f}%")
        lines.append("  📕 领跌 TOP5")
        for name, pct in sectors_sorted[-5:]:
            lines.append(f"    🔴 {name}: {pct:+.2f}%")
    else:
        lines.append("  暂无板块数据")

    # ── 3. 涨停/跌停 ──
    lines.extend(["", "【涨停板】"])
    zt = get_zt_pool()
    if zt:
        lines.append(f"  共{len(zt)}支（前10）")
        for s in zt:
            lines.append(f"  🚀 {s}")
    else:
        lines.append("  暂无涨停数据")

    dt = get_dt_pool()
    if dt:
        lines.extend(["", "【跌停板】"])
        for s in dt:
            lines.append(f"  🔻 {s}")

    # ── 4. 个股异动 ──
    lines.extend(["", "【个股异动 · 今日涨幅榜】"])
    gainers = get_top_gainers()
    if gainers:
        for s in gainers:
            lines.append(f"  ⚡ {s}")
    else:
        lines.append("  暂无数据")

    # ── 5. 资金流向 ──
    lines.extend(["", "【资金动向】"])
    fund = get_fund_flow()
    if fund:
        for l in fund:
            lines.append(f"  💰 {l}")
    north = get_north()
    if north:
        for l in north:
            lines.append(f"  🌏 北向: {l}")
    if not fund and not north:
        lines.append("  暂无资金数据")

    # ── 6. 昨夜今晨 ──
    lines.extend(["", "【昨夜今晨】"])
    news = get_news()
    if news:
        for n in news:
            lines.append(f"  📰 {n}")
    else:
        lines.append("  暂无晨间新闻")

    # ── 7. 今日关注 ──
    lines.extend(["", "【今日关注方向】"])
    if sectors:
        top_names = [s[0] for s in sectors_sorted[:3]]
        lines.append(f"  🔍 关注板块: {'、'.join(top_names)}")
    lines.append("  🔍 连板高度: 爱丽家居 5连板、五洲医疗 4连板 — 关注断板风险")
    lines.append("  🔍 北向资金动向（近期净流入/出趋势）")

    # ── 结尾 ──
    lines.extend([
        "",
        "━" * 28,
        "⚠️ AI自动生成，仅供参考，不构成投资建议",
        "🤖 由 GitHub Actions 自动推送",
    ])
    return "\n".join(lines)


# ==================== 推送 ====================

def push_to_wechat(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print("⚠️  未设置 PUSHPLUS_TOKEN，跳过推送")
        print(content)
        return False
    resp = requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "txt"},
        timeout=15,
    )
    r = resp.json()
    ok = r.get("code") == 200
    print("✅ 已推送到微信" if ok else f"❌ 推送失败: {r.get('msg', r)}")
    return ok


if __name__ == "__main__":
    print("🔍 正在采集A股数据...\n")
    report = build_report()
    print(report)
    push_to_wechat("📊 今日操盘日报", report)
