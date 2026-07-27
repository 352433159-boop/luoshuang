#!/usr/bin/env python3
"""📊 A股投资者日报 —— 技术面·资金面·情绪面·涨停拆解·龙虎榜·汇率·新闻"""

import os, requests
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
DAY = datetime.now(TZ)
TODAY = DAY.strftime("%Y%m%d")
YESTERDAY = (DAY - timedelta(days=1)).strftime("%Y%m%d")

try:
    import akshare as ak
except ImportError:
    raise SystemExit("❌ pip install akshare")


def safe(fn):
    def w(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            return None
    return w


# ──────────────────── 数据采集 ────────────────────

@safe
def get_indices():
    """三大指数涨跌 + 量能（亿）+ 振幅区间"""
    items = []
    for sym, name in [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]:
        df = ak.stock_zh_index_daily(symbol=sym).tail(6)
        if len(df) >= 2:
            c, p = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
            pct = round((c - p) / p * 100, 2)
            vol = int(df["volume"].iloc[-1])                # 最新日成交量
            vol_avg = int(df["volume"].iloc[:-1].mean())    # 前5日均量
            vol_pct = round((vol - vol_avg) / vol_avg * 100, 1)
            vol_yi = round(vol / 1e8, 1)                    # 亿
            high5 = float(df["high"].tail(5).max())
            low5 = float(df["low"].tail(5).min())
            items.append((name, c, pct, vol_yi, vol_pct, high5, low5))
    return items


@safe
def get_market_wide():
    """涨跌家数"""
    df = ak.stock_zh_a_spot_em()
    up = (df["涨跌幅"] > 0).sum()
    down = (df["涨跌幅"] < 0).sum()
    flat = (df["涨跌幅"] == 0).sum()
    zt = (df["涨跌幅"] >= 9.8).sum()
    dt = (df["涨跌幅"] <= -9.8).sum()
    return up, down, flat, zt, dt


@safe
def get_sectors():
    return list(ak.stock_board_industry_name_em()[["板块名称", "涨跌幅"]].itertuples(index=False, name=None))


@safe
def get_concept():
    df = ak.stock_board_concept_name_em()
    return list(df[["板块名称", "涨跌幅"]].itertuples(index=False, name=None))


@safe
def get_zt_detail():
    zt = ak.stock_zt_pool_em(date=TODAY)
    items, cnt = {}, {}
    for _, r in zt.iterrows():
        b = r["连板数"]
        items.setdefault(b, []).append((r["代码"], r["名称"], r.get("所属行业", "未知")))
        ind = r.get("所属行业", "未知")
        cnt[ind] = cnt.get(ind, 0) + 1
    hot = sorted(cnt.items(), key=lambda x: -x[1])[:5]
    return items, hot, len(zt)


@safe
def get_dt_list():
    dt = ak.stock_zt_pool_dtgc_em(date=TODAY)
    return [(r["代码"], r["名称"]) for _, r in dt.iterrows()]


@safe
def get_lhb():
    df = ak.stock_lhb_detail_em(start_date=YESTERDAY, end_date=TODAY)
    if df is None or df.empty:
        return None
    top = df.nlargest(10, "买入金额").head(6)
    return [(r["代码"], r["名称"], float(r.get("买入金额", 0))) for _, r in top.iterrows()]


@safe
def get_north():
    df = ak.stock_hsgt_hist_em(symbol="北上")
    return [(r.iloc[0], float(r.iloc[1])) for _, r in df.tail(5).iterrows()]


@safe
def get_fund():
    f = ak.stock_market_fund_flow()
    return [f"{r.iloc[0]}: 主力{r.iloc[1]:+.0f}亿" for _, r in f.tail(5).iterrows()]


@safe
def get_volume_surge():
    df = ak.stock_zh_a_spot_em()
    df = df[~df["名称"].str.contains("ST|N|C|退", na=False)]
    df = df[df["涨跌幅"] > 3].nlargest(8, "量比")
    return [(r["代码"], r["名称"], r["涨跌幅"], r.get("量比", 1)) for _, r in df.iterrows()]


@safe
def get_news():
    for d in [TODAY, YESTERDAY]:
        try:
            c = ak.news_cctv(date=d)
            if c is not None and not c.empty:
                return [r["title"] for _, r in c.iterrows()
                        if len(r.get("title", "")) > 4 and not r["title"].startswith("《")]
        except:
            continue
    return None


@safe
def get_fx():
    df = ak.fx_spot_quote()
    targets = {"USD/CNY", "EUR/CNY", "100JPY/CNY", "GBP/CNY"}
    return {r["货币对"]: r["买报价"] for _, r in df.iterrows() if r["货币对"] in targets}


# ──────────────────── 报告 ────────────────────

def build_report():
    now = DAY.strftime("%Y年%m月%d日 %A")
    lines = []
    L = lines.append

    L(f"📊 A股投资者日报 · {now}")
    L("━" * 30)

    # ── 1. 隔夜外盘 ──
    L("\n【隔夜外盘】")
    fx = get_fx()
    if fx:
        for k, v in fx.items():
            L(f"  💱 {k}: {v}")
    else:
        L("  暂无汇率数据")

    # ── 2. 大盘技术面 ──
    L("\n【大盘技术面】")
    indices = get_indices()
    if indices:
        idx_up = sum(1 for i in indices if i[2] > 0)
        for name, price, pct, vol_yi, vpct, h5, l5 in indices:
            a = "📈" if pct > 0 else "📉" if pct < 0 else "➖"
            va = "📈放量" if vpct > 5 else "📉缩量" if vpct < -5 else "➖平量"
            L(f"  {name}: {price:.0f}  {a}{pct:+.2f}%  {va}{vpct:+.0f}%")
            L(f"    量{vol_yi}亿  5日区间{h5:.0f}-{l5:.0f}  距高点{(h5-price)/h5*100:.1f}%")
        mood = "偏强 ☀️" if idx_up >= 2 else ("偏弱 🌧️" if idx_up == 0 else "震荡 ⛅")
        L(f"  大盘整体{mood}")
    else:
        L("  暂无数据")

    # ── 3. 全市场情绪 ──
    L("\n【全市场情绪】")
    mw = get_market_wide()
    if mw:
        up, down, flat, zt, dt = mw
        total = up + down + flat
        L(f"  上涨{up}({up/total*100:.0f}%) | 下跌{down}({down/total*100:.0f}%) | 平{flat}")
        L(f"  涨停≥9.8%: {zt}支 | 跌停≤-9.8%: {dt}支")
        rr = round(up / down, 2) if down else float("inf")
        if rr > 2:    L("  情绪面: 普涨格局 🟢")
        elif rr > 1:  L("  情绪面: 多方占优 🟢")
        elif rr > 0.5:L("  情绪面: 空方占优 🔴")
        else:         L("  情绪面: 普跌 🔴")
    else:
        L("  暂无数据")

    # ── 4. 板块轮动 ──
    L("\n【板块轮动】")
    sectors = get_sectors()
    if sectors:
        ss = sorted(sectors, key=lambda x: x[1], reverse=True)
        L("  📗 领涨 TOP8")
        for n, p in ss[:8]: L(f"    🟢 {n}: {p:+.2f}%")
        L("  📕 领跌 TOP8")
        for n, p in ss[-8:]: L(f"    🔴 {n}: {p:+.2f}%")
        L(f"  强势: {'、'.join(n for n,_ in ss[:3])}")
    cs = get_concept()
    if cs:
        css = sorted(cs, key=lambda x: x[1], reverse=True)
        L("\n  概念 TOP5")
        for n, p in css[:5]: L(f"    🔥 {n}: {p:+.2f}%")

    # ── 5. 涨停拆解 ──
    L("\n【涨停拆解】")
    zt_r = get_zt_detail()
    if zt_r:
        bg, hot, zt_n = zt_r
        max_b = max(bg.keys())
        L(f"  涨停 {zt_n}支 | 最高 {max_b}连板")
        for b in sorted(bg.keys(), reverse=True)[:3]:
            st = bg[b]
            L(f"    {b}连板({len(st)}支): {' '.join(f'{n}({c})' for c,n,_ in st[:5])}")
        L(f"  📊 涨停板块分布")
        for ind, cnt in hot:
            L(f"    {'█'*cnt} {ind}: {cnt}支")
        if hot: L(f"  💡 {hot[0][0]}批量涨停{hot[0][1]}支")
        L(f"  💡 龙头{max_b}连板{bg[max_b][0][1]}，关注断板")
    else:
        L("  暂无涨停")

    dt_l = get_dt_list()
    if dt_l:
        L(f"\n【跌停板】{len(dt_l)}支")
        for c, n in dt_l[:8]: L(f"  🔻 {c} {n}")

    # ── 6. 龙虎榜 ──
    L("\n【龙虎榜】")
    lhb = get_lhb()
    if lhb:
        for c, n, amt in lhb:
            L(f"  🐅 {c} {n}  买入{amt/1e4:.0f}万")
    else:
        L("  暂无龙虎榜")

    # ── 7. 放量异动 ──
    L("\n【放量异动】")
    surges = get_volume_surge()
    if surges:
        for c, n, pct, ratio in surges:
            L(f"  ⚡ {c} {n}  {pct:+.1f}%  量比{ratio:.1f}")
    else:
        L("  暂无数据")

    # ── 8. 资金 ──
    L("\n【资金流向】")
    fund = get_fund()
    if fund:
        for l in fund: L(f"  💰 {l}")
    north = get_north()
    if north:
        for d, v in north:
            a = "📈" if v > 0 else "📉"
            L(f"  🌏 北向 {d}: {a}{v:+.0f}亿")
    if not fund and not north: L("  暂无资金数据")

    # ── 9. 昨夜今晨 ──
    L("\n【昨夜今晨】")
    news = get_news()
    if news:
        for n in news[:6]: L(f"  📰 {n}")
    else:
        L("  暂无晨间新闻")

    # ── 10. 综合研判 ──
    L("\n【综合研判】")
    if indices:
        idx_up = sum(1 for i in indices if i[2] > 0)
        mood = "偏弱" if idx_up == 0 else ("偏强" if idx_up >= 2 else "震荡")
        L(f"  大盘{mood}")
    else:
        L("  大盘数据缺失")

    if zt_r:
        _, _, zt_n = zt_r
        eff = "较好 📈" if zt_n > 50 else ("一般 📊" if zt_n > 20 else "偏差 📉")
        L(f"  涨停{zt_n}支，赚钱效应{eff}")

    if indices and zt_r:
        bg, _, _ = zt_r
        max_b = max(bg.keys())
        if idx_up == 0 and zt_n > 50:
            L(f"  ⚠️ 指数普跌但涨停{zt_n}支，结构分化明显，精做个股")
        elif idx_up == 0:
            L(f"  ⚠️ 三大指数齐跌，建议控制仓位观望")
        elif max_b >= 4:
            L(f"  连板高度{max_b}，短线情绪尚可")

    if indices:
        vol_descs = [f"{i[0]}量{i[3]}亿({i[4]:+.0f}%)" for i in indices]
        L(f"  量能: {' '.join(vol_descs)}")
        if all(i[4] < 0 for i in indices):
            L("  ⚠️ 三大指数同步缩量，市场观望情绪重")
        elif any(abs(i[4]) > 15 for i in indices):
            L("  ⚠️ 出现明显量能异动，注意方向选择")

    L("\n  📌 AI生成·仅供参考")

    L("\n━" * 30)
    L("🤖 GitHub Actions 自动推送")
    return "\n".join(lines)


# ──────────────────── 推送 ────────────────────

def push(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print(content)
        return
    r = requests.post("https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "txt"}, timeout=15).json()
    print("✅ 已推送到微信" if r.get("code") == 200 else f"❌ {r}")


if __name__ == "__main__":
    print("🔍 采集数据...\n")
    rpt = build_report()
    print(rpt)
    push("📊 A股投资者日报", rpt)
