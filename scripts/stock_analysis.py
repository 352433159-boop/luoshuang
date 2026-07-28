#!/usr/bin/env python3
"""📈 个股深度分析 —— yfinance + akshare 双数据源"""
import os, sys, requests
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
CODE = os.environ.get("STOCK_CODE", "").strip()
NAME = os.environ.get("STOCK_NAME", "").strip()
if not CODE:
    sys.exit("❌ 请设置 STOCK_CODE")
SUFFIX = os.environ.get("STOCK_MARKET", "sz").lower()
YF_SUFFIX = ".SZ" if SUFFIX == "sz" else ".SS"
YF_TICKER = CODE + YF_SUFFIX

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("❌ pip install yfinance requests")


def safe(fn):
    def w(*a, **kw):
        try: return fn(*a, **kw)
        except Exception as e:
            return None
    return w


# ─── Data ───

@safe
def get_info():
    """股票基本信息 + 财务指标"""
    tk = yf.Ticker(YF_TICKER)
    info = tk.info
    if not info: return None
    return {
        "name": info.get("longName", info.get("shortName", NAME or CODE)),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "prev_close": info.get("previousClose"),
        "pct": info.get("regularMarketChangePercent"),
        "pe": info.get("trailingPE") or info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "mcap": info.get("marketCap"),
        "roe": info.get("returnOnEquity"),
        "profit_margin": info.get("profitMargins"),
        "debt": info.get("debtToEquity"),
        "dividend_yield": info.get("dividendYield"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "recommendation": info.get("recommendationKey"),
        "target": info.get("targetMeanPrice"),
        "high52": info.get("fiftyTwoWeekHigh"),
        "low52": info.get("fiftyTwoWeekLow"),
    }


@safe
def get_history(days=120):
    """历史日线数据"""
    tk = yf.Ticker(YF_TICKER)
    df = tk.history(period=f"{days}d", interval="1d")
    if df is None or df.empty:
        return None
    df = df.tail(days)
    close = df["Close"].values
    high = df["High"].values
    low = df["Low"].values
    vol = df["Volume"].values
    last = float(close[-1])
    pct_30 = (last/float(close[-30])-1)*100 if len(close)>=30 else 0
    pct_60 = (last/float(close[-60])-1)*100 if len(close)>=60 else 0
    ma5 = float(df["Close"].tail(5).mean())
    ma20 = float(df["Close"].tail(20).mean())
    ma60 = float(df["Close"].tail(60).mean())
    h60 = max(high[-60:]) if len(high)>=60 else max(high)
    l60 = min(low[-60:]) if len(low)>=60 else min(low)
    vol_5 = vol[-5:].mean() if len(vol)>=5 else vol.mean()
    vol_60 = vol[-60:].mean() if len(vol)>=60 else vol.mean()
    return {
        "price": last, "h60": h60, "l60": l60,
        "pct30": pct_30, "pct60": pct_60,
        "ma5": ma5, "ma20": ma20, "ma60": ma60,
        "vol_ratio": vol_5/vol_60 if vol_60 else 1,
    }


@safe
def get_income():
    """利润表"""
    tk = yf.Ticker(YF_TICKER)
    inc = tk.income_stmt
    if inc is None or inc.empty: return None
    result = []
    for col in inc.columns[:4]:
        rev = inc.loc.get("Total Revenue", inc.loc.get("Operating Revenue"))
        ni = inc.loc.get("Net Income")
        if rev is not None and ni is not None:
            rev_v = float(rev.get(col, 0))
            ni_v = float(ni.get(col, 0))
            if rev_v > 0:
                result.append((str(col)[:10], rev_v/1e8, ni_v/1e8, ni_v/rev_v*100))
    return result


@safe
def get_balance():
    """资产负债表关键指标"""
    tk = yf.Ticker(YF_TICKER)
    bs = tk.balance_sheet
    if bs is None or bs.empty: return None
    col = bs.columns[0]
    cash = bs.loc.get("Cash And Cash Equivalents")
    debt = bs.loc.get("Total Debt", bs.loc.get("Long Term Debt"))
    equity = bs.loc.get("Stockholders Equity")
    return {
        "cash": float(cash.get(col, 0))/1e8 if cash is not None else None,
        "debt": float(debt.get(col, 0))/1e8 if debt is not None else None,
        "equity": float(equity.get(col, 0))/1e8 if equity is not None else None,
    }


# ─── Report ───

def build():
    day = datetime.now(TZ).strftime("%Y年%m月%d日 %H:%M")
    display = NAME or CODE
    L = [f"📈 {display}({CODE}) 深度分析 · {day}", "━"*24]

    # 1. 基本信息
    info = get_info()
    if info:
        L.append(f"\n【公司概况】")
        L.append(f"  {info.get('name','?')}")
        L.append(f"  行业: {info.get('sector','?')} - {info.get('industry','?')}")
        price = info.get("price")
        if price:
            pct = info.get("pct", 0)
            pct_val = pct * 100 if abs(pct) < 1 else pct  # yfinance有时返回小数
            a = "📈" if pct_val > 0 else "📉"
            L.append(f"  最新价: {price:.2f}  {a}{pct_val:+.2f}%")
        L.append(f"  市盈率PE: {info.get('pe','?')}  市净率PB: {info.get('pb','?')}")
        L.append(f"  总市值: {info.get('mcap',0)/1e8:.0f}亿")
        if info.get("dividend_yield"):
            L.append(f"  股息率: {info['dividend_yield']*100:.2f}%")
        if info.get("recommendation"):
            L.append(f"  机构评级: {info['recommendation']}")
        if info.get("target"):
            L.append(f"  机构目标价: {info['target']:.2f}")
    else:
        L.append(f"\n暂无行情数据")

    # 2. 技术面
    hist = get_history()
    if hist:
        L.append(f"\n【技术面】(近60日)")
        L.append(f"  当前{hist['price']:.2f}  最高{hist['h60']:.2f}  最低{hist['l60']:.2f}")
        L.append(f"  近30日: {hist['pct30']:+.2f}%  近60日: {hist['pct60']:+.2f}%")
        L.append(f"  MA5:{hist['ma5']:.2f}  MA20:{hist['ma20']:.2f}  MA60:{hist['ma60']:.2f}")
        pos = f"当前价在MA20{'上📈' if hist['price']>hist['ma20'] else '下📉'}"
        pos += f"，MA60{'上📈' if hist['price']>hist['ma60'] else '下📉'}"
        L.append(f"  {pos}")
        # 趋势
        if hist["price"] > hist["ma20"] > hist["ma60"]: L.append("  趋势: 多头排列✅")
        elif hist["price"] < hist["ma20"] < hist["ma60"]: L.append("  趋势: 空头排列❌")
        else: L.append("  趋势: 方向不明⚠️")
        # 量能
        vr = hist["vol_ratio"]
        L.append(f"  量能: {'放量' if vr>1.2 else '缩量' if vr<0.8 else '正常'}(均量{vr:.2f}倍)")
    else:
        L.append(f"\n暂无技术数据")

    # 3. 财务面
    L.append(f"\n【财务面】")
    inc = get_income()
    if inc:
        for p, rev, ni, margin in inc:
            L.append(f"  {p}: 营收{rev:.0f}亿  净利{ni:.0f}亿  净利率{margin:.1f}%")
    if info:
        roe = info.get("roe")
        pm = info.get("profit_margin")
        debt = info.get("debt")
        if roe: L.append(f"  ROE: {roe*100:.1f}%")
        if pm: L.append(f"  净利率: {pm*100:.1f}%")
        if debt is not None: L.append(f"  负债/权益: {debt:.1f}%")
    bs = get_balance()
    if bs:
        if bs.get("cash"): L.append(f"  现金: {bs['cash']:.0f}亿")
        if bs.get("debt"): L.append(f"  负债: {bs['debt']:.0f}亿")
    if not inc and not bs: L.append("  暂无财务数据")

    # 4. 估值区间
    if hist:
        L.append(f"\n【估值区间】")
        price = hist["price"]
        dist_high = (price - hist["h60"]) / hist["h60"] * 100
        dist_low = (price - hist["l60"]) / hist["l60"] * 100
        L.append(f"  距60日高{hist['h60']:.2f}: {dist_high:+.1f}%")
        L.append(f"  距60日低{hist['l60']:.2f}: {dist_low:+.1f}%")
        if dist_low < 5: L.append("  📗 靠近低点，可关注")
        elif dist_high > -5: L.append("  📕 靠近高点，追高风险")
        else: L.append("  ⏳ 中间位置，等待方向")

    # 5. 综合
    L.append(f"\n【综合研判】")
    if hist and info:
        score = 0
        if info.get("pe") and info["pe"] < 20: score+=1
        if hist["price"] > hist["ma20"]: score+=1
        if hist["price"] > hist["ma60"]: score+=1
        dist_low_val = (hist["price"] - hist["l60"]) / hist["l60"] * 100
        if dist_low_val < 5: score+=1
        adv = {5:"强烈关注🌟",4:"可关注✅",
               3:"中性观望⚖️",2:"谨慎🔻",
               1:"回避❌",0:"回避❌"}.get(score, "观望")
        L.append(f"  评分: {score}/5 → {adv}")
        if info.get("recommendation") == "buy": L.append(f"  机构建议: 买入")
        elif info.get("recommendation") == "hold": L.append(f"  机构建议: 持有")
        elif info.get("recommendation") == "sell": L.append(f"  机构建议: 卖出")
    L.append(f"\n{'━'*24}")
    L.append("🤖 AI分析·仅供参考")

    return "\n".join(L)


def push(title, content):
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token: print(content); return
    if len(content) > 1800: content = content[:1700] + "\n\n(已截断)"
    r = requests.post("https://www.pushplus.plus/send",
        json={"token": token, "title": title, "content": content, "template": "txt"}, timeout=15)
    j = r.json()
    print("✅ 推送成功" if j.get("code") == 200 else f"❌ 推送失败")


if __name__ == "__main__":
    print(f"🔍 {display} 分析中...\n")
    rpt = build()
    print(rpt)
    push(f"📈 {display} 深度分析", rpt)
