#!/usr/bin/env python3
"""A股深度日报：大盘 + 板块 + 量能 + 涨停深度分析 + 资金流向 + 昨夜今晨"""

import os
import requests
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y%m%d")
YESTERDAY = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y%m%d")
YESTERDAY_TWO = (datetime.now(TZ) - timedelta(days=2)).strftime("%Y%m%d")

try:
    import akshare as ak
except ImportError:
    print("❌ 缺少 akshare，请运行: pip install akshare")
    raise


# ==================== 采集 ====================

def safe(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            return None
    return wrapper


@safe
def get_indices_detail():
    """三大指数涨跌幅 + 成交量"""
    items = []
    for symbol, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        df = ak.stock_zh_index_daily(symbol=symbol).tail(5)
        if len(df) >= 2:
            c_latest = float(df["close"].iloc[-1])
            c_prev = float(df["close"].iloc[-2])
            pct = round((c_latest - c_prev) / c_prev * 100, 2)

            vol_latest = int(df["volume"].iloc[-1])
            vol_prev_avg = int(df["volume"].iloc[-6:-1].mean()) if len(df) >= 5 else vol_latest
            vol_pct = round((vol_latest - vol_prev_avg) / vol_prev_avg * 100, 2)

            # 涨跌家数
            line = f"{name}: {c_latest:.0f}  {pct:+.2f}%  量{vol_pct:+.0f}%"
            items.append((name, c_latest, pct, vol_pct, line))
    return items


@safe
def get_sector_rankings(n=8):
    """板块涨跌幅 TOP & BOTTOM"""
    df = ak.stock_board_industry_name_em()
    return list(df[["板块名称", "涨跌幅"]].itertuples(index=False, name=None))


@safe
def get_zt_pool_detail():
    """涨停板详细分析"""
    zt = ak.stock_zt_pool_em(date=TODAY)
    if zt is None or zt.empty:
        return None, None, None
    items = []
    sector_map = {}
    for _, r in zt.iterrows():
        code = r.get("代码", "?")
        name = r.get("名称", "?")
        board = r.get("连板数", 1)
        industry = r.get("所属行业", "未知")
        items.append((code, name, board, industry))
        sector_map[industry] = sector_map.get(industry, 0) + 1
    hot_sectors = sorted(sector_map.items(), key=lambda x: -x[1])[:5]
    return items, hot_sectors, len(zt)


@safe
def get_dt_pool():
    """跌停板"""
    dt = ak.stock_zt_pool_dtgc_em(date=TODAY)
    return [f"{r['代码']} {r['名称']}" for _, r in dt.head(8).iterrows()]


@safe
def get_top_gainers(n=10):
    """今日涨幅榜（排除st、新股）"""
    df = ak.stock_zh_a_spot_em()
    df = df[~df["名称"].str.contains("ST|N|C|退", na=False)]
    top = df.nlargest(n, "涨跌幅")
    items = []
    for _, r in top.iterrows():
        items.append({
            "code": r["代码"],
            "name": r["名称"],
            "pct": r["涨跌幅"],
            "price": r["最新价"],
            "volume": r.get("成交额", 0),
            "turnover": r.get("换手率", 0),
        })
    return items


@safe
def get_volume_anomaly():
    """量比异常的个股（涨幅居前 + 放量）"""
    df = ak.stock_zh_a_spot_em()
    df = df[~df["名称"].str.contains("ST|N|C|退", na=False)]
    df = df[df["涨跌幅"] > 3]
    top = df.nlargest(8, "量比")
    return [(r["代码"], r["名称"], r["涨跌幅"], r.get("量比", 0)) for _, r in top.iterrows()]


@safe
def get_news():
    """昨夜今晨新闻"""
    items = []
    for d in [TODAY, YESTERDAY, YESTERDAY_TWO]:
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
    return items[:8]


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


# ==================== 报告 ====================

def build_report():
    now = datetime.now(TZ).strftime("%Y年%m月%d日 %A")
    lines = [f"📊 深度操盘日报 · {now}", "━" * 28]

    # ── 1. 大盘回顾（含量能）──
    lines.extend(["", "【大盘回顾 + 量能分析】"])
    indices = get_indices_detail()
    if indices:
        up = sum(1 for i in indices if i[2] > 0)
        for _, _, _, _, line in indices:
            lines.append(f"  {line}")
        mood = "偏强 ☀️" if up >= 2 else ("偏弱 🌧️" if up == 0 else "震荡 ⛅")
        lines.append(f"  大盘整体{mood}")
        # 量能综合判断
        vol_ups = sum(1 for i in indices if i[3] > 0)
        vol_names = [i[0] for i in indices if abs(i[3]) > 5]
        if vol_ups >= 2:
            lines.append("  量能分析: 三大指数普遍放量，市场交投活跃 📈")
        elif vol_ups == 0 and vol_names:
            lines.append(f"  量能分析: {'、'.join(vol_names)}缩量明显，市场观望情绪较重 📉")
        elif vol_names:
            lines.append(f"  量能分析: {'、'.join(vol_names)}出现明显量能异动 ⚡")
        else:
            lines.append("  量能分析: 成交量无明显异常")
    else:
        lines.append("  暂无指数数据")

    # ── 2. 板块轮动 + 分析 ──
    lines.extend(["", "【板块轮动分析】"])
    sectors = get_sector_rankings()
    if sectors:
        s_sorted = sorted(sectors, key=lambda x: x[1], reverse=True)
        lines.append("  📗 领涨 TOP8")
        for name, pct in s_sorted[:8]:
            lines.append(f"    🟢 {name}: {pct:+.2f}%")
        lines.append("  📕 领跌 TOP8")
        for name, pct in s_sorted[-8:]:
            lines.append(f"    🔴 {name}: {pct:+.2f}%")
        # 板块分析
        top_s = s_sorted[:3]
        bot_s = s_sorted[-3:]
        lines.append(f"  💡 强势板块: {'、'.join(n for n, _ in top_s)} 涨幅居前")
        lines.append(f"  💡 弱势板块: {'、'.join(n for n, _ in bot_s)} 回调明显")
    else:
        lines.append("  暂无板块数据")

    # ── 3. 涨停深度分析 ──
    lines.extend(["", "【涨停深度分析】"])
    zt_result = get_zt_pool_detail()
    zt_items = hot_sectors = zt_count = None
    max_board = 0
    if zt_result:
        zt_items, hot_sectors, zt_count = zt_result
        if zt_items:
            board_groups = {}
            for code, name, board, ind in zt_items:
                board_groups.setdefault(board, []).append((code, name, ind))
            max_board = max(board_groups.keys())
    if zt_items:
        lines.append(f"  今日涨停 {zt_count} 支")
        # 按连板数分组
        board_groups = {}
        for code, name, board, ind in zt_items:
            board_groups.setdefault(board, []).append((code, name, ind))
        max_board = max(board_groups.keys())
        lines.append(f"  🔥 最高连板: {max_board}连板")
        for b in sorted(board_groups.keys(), reverse=True)[:3]:
            stocks = board_groups[b]
            names = "、".join(f"{n}({c})" for c, n, _ in stocks)
            lines.append(f"    {b}连板股({len(stocks)}支): {names}")
        # 涨停板块分布
        lines.append("  📊 涨停板块分布")
        for ind, cnt in hot_sectors:
            bar = "█" * cnt
            lines.append(f"    {bar} {ind}: {cnt}支")
        # 涨停综合分析
        if hot_sectors and hot_sectors[0][1] >= 3:
            lines.append(f"  💡 {hot_sectors[0][0]}板块出现批量涨停({hot_sectors[0][1]}支)，板块效应明显")
        top_ind = hot_sectors[0][0] if hot_sectors else ""
        top_cnt = hot_sectors[0][1] if hot_sectors else 0
        if top_cnt >= 5:
            lines.append(f"  💡 {top_ind}板块涨停潮，可能存在政策或消息面催化")
        lines.append(f"  💡 连板梯队: {max_board}连板→...，关注龙头股次日表现")
    else:
        lines.append("  暂无涨停数据")

    # 跌停
    dt = get_dt_pool()
    if dt:
        lines.extend(["", "【跌停板】"])
        for s in dt:
            lines.append(f"  🔻 {s}")
        lines.append("  ⚠️ 风险提示: 跌停股以中小市值为主，注意流动性风险")

    # ── 4. 异动放量个股 ──
    lines.extend(["", "【异动放量榜】"])
    anomalies = get_volume_anomaly()
    if anomalies:
        lines.append("  (涨幅 > 3% 且量比居前的个股)")
        for code, name, pct, ratio in anomalies:
            lines.append(f"  ⚡ {code} {name} 涨幅{pct:+.1f}% 量比{ratio:.1f}")
        max_ratio = anomalies[0][3] if anomalies else 0
        if max_ratio > 5:
            lines.append(f"  💡 {anomalies[0][1]}量比{max_ratio:.1f}，放量明显，关注后续方向")
    else:
        lines.append("  暂无数据")

    # ── 5. 个股涨幅榜 ──
    lines.extend(["", "【涨幅榜 TOP10】"])
    gainers = get_top_gainers()
    if gainers:
        for g in gainers:
            lines.append(f"  📗 {g['code']} {g['name']}  {g['pct']:+.2f}%  换手{g['turnover']:.1f}%")
        # 趋势分析
        avg_turnover = sum(g["turnover"] for g in gainers) / len(gainers)
        if avg_turnover > 10:
            lines.append("  💡 涨幅榜个股平均换手率超过10%，短线博弈激烈")
        elif avg_turnover < 3:
            lines.append("  💡 涨幅榜个股换手率偏低，可能为趋势股而非游资炒作")
    else:
        lines.append("  暂无数据")

    # ── 6. 资金流向 ──
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

    # ── 7. 昨夜今晨 ──
    lines.extend(["", "【昨夜今晨重要新闻】"])
    news = get_news()
    if news:
        for n in news:
            lines.append(f"  📰 {n}")
    else:
        lines.append("  暂无晨间新闻")

    # ── 8. 综合研判 ──
    lines.extend(["", "【综合研判】"])
    if indices and zt_items:
        idx_up = sum(1 for i in indices if i[2] > 0)
        mood_text = "偏弱 🌧️" if idx_up == 0 else ("震荡偏强 ☀️" if idx_up >= 2 else "震荡 ⛅")
        hot_text = ""
        if hot_sectors:
            hot_text = f"，{'、'.join(n for n,_ in hot_sectors[:2])}表现活跃"
        lines.append(f"  ① 大盘{mood_text}，涨停{zt_count}支{hot_text}")
        zt_fen = "较好 📈" if zt_count > 50 else ("一般 📊" if zt_count > 20 else "偏差 📉")
        lines.append(f"  ② 涨停数量{zt_count}支，赚钱效应{zt_fen}")
        if max_board >= 4:
            lines.append(f"  ③ 连板高度{max_board}板，短线情绪尚可，关注龙头断板风险")
        elif max_board >= 2:
            lines.append(f"  ③ 连板高度{max_board}板，短线炒作偏弱")
        if sectors:
            s_sorted = sorted(sectors, key=lambda x: x[1], reverse=True)
            lines.append(f"  ④ 板块方面，强势板块{'、'.join(n for n,_ in s_sorted[:2])} 可关注持续性")
        elif idx_up == 0:
            lines.append(f"  ④ 三大指数齐跌+缩量，短期情绪偏悲观，建议观望为主")
    else:
        lines.append("  数据不足，无法综合研判")

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
        return
    resp = requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "txt"},
        timeout=15,
    )
    r = resp.json()
    ok = r.get("code") == 200
    print("✅ 已推送到微信" if ok else f"❌ 推送失败: {r.get('msg', r)}")


if __name__ == "__main__":
    print("🔍 正在采集A股多维度数据...\n")
    report = build_report()
    print(report)
    push_to_wechat("📊 深度操盘日报", report)
