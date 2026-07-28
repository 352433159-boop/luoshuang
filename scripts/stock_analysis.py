#!/usr/bin/env python3
"""📈 个股深度分析 —— 实时行情·技术面·财务面·估值"""
import os, sys, requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal
TZ = timezone(timedelta(hours=8))

# 取参数
stock_code = os.environ.get("STOCK_CODE", "")
stock_name = os.environ.get("STOCK_NAME", "")
market = os.environ.get("STOCK_MARKET", "sz")
if not stock_code:
    print("❌ 请设置环境变量 STOCK_CODE")
    sys.exit(1)

try:
    import akshare as ak
except ImportError:
    raise SystemExit("❌ pip install akshare")


def safe(fn):
    def w(*a, **kw):
        try: return fn(*a, **kw)
        except: return None
    return w


# ─── 数据采集 ───

@safe
def get_realtime():
    """实时行情"""
    df = ak.stock_zh_a_spot_em()
    s = df[df['代码'] == stock_code]
    if s.empty: return None
    r = s.iloc[0]
    return {
        "price": r["最新价"], "pct": r["涨跌幅"],
        "open": r["今开"], "high": r["最高"], "low": r["最低"],
        "vol": r["成交量"]/1e8, "amt": r["成交额"]/1e8,
        "turnover": r["换手率"], "pe": r.get("市盈率-动态","?"),
        "pb": r.get("市净率","?"), "mcap": r["总市值"]/1e8,
    }


@safe
def get_technical(n=90):
    """技术面"""
    start = (datetime.now(TZ) - timedelta(days=n*2)).strftime("%Y%m%d")
    end = datetime.now(TZ).strftime("%Y%m%d")
    df = ak.stock_zh_a_hist(symbol=stock_code, period="daily",
                            start_date=start, end_date=end, adjust="qfq")
    if df is None or df.empty: return None
    close = df["收盘"].values
    high = df["最高"].values
    low = df["最低"].values
    last = float(close[-1])
    pct_30d = (last/float(close[-30])-1)*100 if len(close)>=30 else 0
    pct_60d = (last/float(close[-60])-1)*100 if len(close)>=60 else 0
    ma5 = float(df["收盘"].tail(5).mean())
    ma20 = float(df["收盘"].tail(20).mean())
    ma60 = float(df["收盘"].tail(60).mean())
    h60 = max(high[-60:]) if len(high)>=60 else max(high)
    l60 = min(low[-60:]) if len(low)>=60 else min(low)
    # 量能
    vol = df["成交量"].values
    vol_5avg = vol[-5:].mean() if len(vol)>=5 else vol.mean()
    vol_60avg = vol[-60:].mean() if len(vol)>=60 else vol.mean()
    vol_ratio = vol_5avg/vol_60avg if vol_60avg else 1
    return {
        "price": last, "high60": h60, "low60": l60,
        "pct30": pct_30d, "pct60": pct_60d,
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
        "vol_ratio": vol_ratio,
    }


@safe
def get_finance():
    """财务数据"""
    # 利润表
    inc = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
    items = []
    if inc is not None:
        for _, r in inc.head(4).iterrows():
            op = float(r.get("营业总收入", 0))
            np_ = float(r.get("净利润", 0))
            if op > 0:
                items.append((r["报告期"][:10], op/1e8, np_/1e8, np_/op*100))
    # 主要指标（ROE等）
    idx = ak.stock_financial_abstract_em(symbol=stock_code)
    idx_data = {}
    if idx is not None:
        for _, r in idx.head(1).iterrows():
            idx_data["roe"] = r.get("净资产收益率", "?")
            idx_data["gross_margin"] = r.get("毛利率", "?")
            idx_data["debt_ratio"] = r.get("资产负债率", "?")
    return {"income": items, "indicators": idx_data}


@safe
def get_north_flow():
    """北向资金"""
    n = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
    if n is not None and not n.empty:
        return float(n.iloc[-1, 1])


# ─── 报告生成 ───

def build():
    day = datetime.now(TZ).strftime("%Y年%m月%d日 %H:%M")
    name = stock_name or stock_code
    L = [f"📈 {name}({stock_code}) 深度分析 · {day}", "━"*26]

    # 1. 实时行情
    rt = get_realtime()
    if rt:
        L.append(f"\n【实时行情】")
        a = "📈" if rt["pct"]>0 else "📉"
        L.append(f"  最新价: {rt['price']}  {a}{rt['pct']:+.2f}%")
        L.append(f"  开{rt['open']}  高{rt['high']}  低{rt['low']}")
        L.append(f"  成交{rt['vol']:.1f}亿  额{rt['amt']:.1f}亿")
        L.append(f"  换手{rt['turnover']}%  PE{rt['pe']}  PB{rt['pb']}")
        L.append(f"  总市值{rt['mcap']:.0f}亿")
    else:
        L.append(f"\n暂无实时数据")

    # 2. 技术面
    tech = get_technical()
    if tech:
        L.append(f"\n【技术面】(近60日)")
        L.append(f"  当前{tech['price']:.2f}  最高{tech['high60']:.2f}  最低{tech['low60']:.2f}")
        L.append(f"  近30日: {tech['pct30']:+.2f}%  近60日: {tech['pct60']:+.2f}%")
        L.append(f"  MA5:{tech['ma5']:.2f}  MA20:{tech['ma20']:.2f}  MA60:{tech['ma60']:.2f}")
        pos = f"当前价在MA20{'上📈' if tech['price']>tech['ma20'] else '下📉'}"
        pos += f"，MA60{'上📈' if tech['price']>tech['ma60'] else '下📉'}"
        L.append(f"  {pos}")
        # 趋势判断
        if tech["price"] > tech["ma20"] > tech["ma60"]:
            L.append(f"  趋势: 多头排列，中期看涨 ✅")
        elif tech["price"] < tech["ma20"] < tech["ma60"]:
            L.append(f"  趋势: 空头排列，中期看跌 ❌")
        elif tech["price"] > tech["ma20"] and tech["price"] < tech["ma60"]:
            L.append(f"  趋势: 短期企稳但中期仍承压，观望 ⚠️")
        else:
            L.append(f"  趋势: 方向不明朗")
        # 量能
        vr = tech["vol_ratio"]
        if vr > 1.5: L.append(f"  量能: 近期放量{vr:.1f}倍，关注突破方向 🔥")
        elif vr < 0.7: L.append(f"  量能: 近期缩量(均量{vr:.0%})，市场关注度下降")
        else: L.append(f"  量能: 正常水平")
    else:
        L.append(f"\n暂无技术数据")

    # 3. 财务面
    fin = get_finance()
    if fin and fin["income"]:
        L.append(f"\n【财务数据】(最近4期)")
        for period, rev, profit, margin in fin["income"]:
            L.append(f"  {period}: 营收{rev:.0f}亿  净利{profit:.0f}亿  净利率{margin:.1f}%")
        if fin["indicators"]:
            ind = fin["indicators"]
            L.append(f"  ROE: {ind.get('roe','?')}%  毛利率: {ind.get('gross_margin','?')}%  负债率: {ind.get('debt_ratio','?')}%")
    else:
        L.append(f"\n暂无财务数据")

    # 4. 估值区间
    if rt and tech:
        L.append(f"\n【估值与建议】")
        price = rt["price"]
        h60, l60 = tech["high60"], tech["low60"]
        mid = (h60 + l60) / 2
        pct_from_high = (price - h60) / h60 * 100
        pct_from_low = (price - l60) / l60 * 100
        L.append(f"  距60日高点{h60}: {pct_from_high:+.1f}%")
        L.append(f"  距60日低点{l60}: {pct_from_low:+.1f}%")
        if pct_from_high > -5:
            L.append(f"  ⚠️ 接近60日高点，不建议追高")
        elif pct_from_low < 10:
            L.append(f"  💡 接近60日低点，可关注逢低机会")
        else:
            L.append(f"  ⏳ 处于中间位置，等待方向选择")

    # 5. 综合研判
    L.append(f"\n【综合研判】")
    if rt and tech:
        score = 0
        reasons = []
        # 估值
        pe_str = str(rt.get("pe","?"))
        try:
            pe = float(pe_str.replace(",",""))
            if pe < 15: score += 1; reasons.append("PE<15，估值偏低")
            elif pe < 25: reasons.append("PE适中")
            else: score -= 1; reasons.append("PE偏高")
        except: pass
        # 趋势
        if tech["price"] > tech["ma20"]: score += 1; reasons.append("站上MA20")
        else: score -= 1; reasons.append("在MA20下方")
        if tech["price"] > tech["ma60"]: score += 1; reasons.append("站上MA60")
        # 位置
        if pct_from_low < 10: score += 1; reasons.append("接近60日低点")
        elif pct_from_high > -5: score -= 1; reasons.append("接近60日高点")

        total = f"综合评分: {score}/5"
        adv = "可关注 📗" if score >= 2 else ("观望 ⚠️" if score >= 0 else "谨慎 🔴")
        L.append(f"  {total} → {adv}")
        for r in reasons: L.append(f"  • {r}")
    else:
        L.append(f"  数据不足")

    L.extend([f"\n{'━'*26}", "🤖 AI自动分析 · 不构成投资建议"])
    return "\n".join(L)


def push(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print(content)
        return
    if len(content) > 1800:
        content = content[:1700] + "\n\n(内容较长，已截断)"
    r = requests.post("https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "txt"}, timeout=15).json()
    print("✅ 已推送" if r.get("code") == 200 else f"❌ {r}")


if __name__ == "__main__":
    print(f"🔍 正在分析 {stock_name or stock_code}...\n")
    rpt = build()
    print(rpt)
    push(f"📈 {stock_name or stock_code} 深度分析", rpt)
