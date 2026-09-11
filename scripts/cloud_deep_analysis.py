#!/usr/bin/env python3
"""云端兜底版盘中深度解读：不依赖本机 Codex，自动生成并推送微信。"""

import importlib.util
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
REPORTS_DIR = REPO_ROOT / "reports"
TZ = timezone(timedelta(hours=8))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cfr = _load_module("cloud_fund_report", SCRIPT_DIR / "cloud_fund_report.py")
sys.path.insert(0, str(SCRIPT_DIR))
import news_alerts  # noqa: E402


SECTOR_ETF = dict(cfr.ETF_MAP)
SECTOR_ETF.update(
    {
        "电网": "sh561380",
        "绿电": "sh562960",
        "低空": "sz159392",
        "债券": "sh511260",
        "欧洲": "sh513030",
    }
)

MAJOR_ETFS = [
    ("黄金", "sh518880"),
    ("A股宽基", "sz159338"),
    ("半导体", "sh512760"),
    ("机器人/AI", "sz159819"),
    ("港股", "sh513050"),
    ("新能源", "sh515790"),
    ("红利", "sh515180"),
    ("军工", "sh512660"),
    ("稀土", "sh516780"),
    ("通信/AI算力", "sh515880"),
    ("绿电", "sh562960"),
    ("电网设备", "sh561380"),
    ("低空", "sz159392"),
    ("医药", "sz159938"),
    ("银行", "sh512800"),
    ("券商", "sh512880"),
]


def _fmt_chg(chg):
    if chg is None:
        return "—"
    text = f"{chg:+.2f}%"
    if chg >= 3 or chg <= -3:
        return f"<span style='color:#e60000;'>{text}</span>"
    return text


def _recent_news():
    keywords = ["A股 收盘", "半导体 芯片", "黄金 金价", "港股 恒生", "机器人 AI", "通信 ETF"]
    out = []
    seen = set()
    for keyword in keywords:
        try:
            articles = news_alerts.search_news(keyword)
        except Exception:
            continue
        for article in articles[:3]:
            title = re.sub(r"</?em>", "", article.get("title", "")).strip()
            date = article.get("date", "")[:16]
            if not title or title in seen:
                continue
            seen.add(title)
            out.append(f"{date}｜{title}")
    return out[:5]


def _operation_lines(fund_data, quotes):
    lines = []
    plan = {
        "006503": ("财通集成电路产业股票C 006503", 1.05, 1.08, 0.95, "分批减仓或换008887"),
        "024688": ("富国国证通用航空产业ETF联接A 024688", 1.03, 1.05, 0.93, "分批清仓"),
        "011035": ("嘉实中证稀土产业ETF联接A 011035", 1.05, 1.08, 0.95, "减半"),
        "160125": ("南方香港优选股票(QDII-LOF) 160125", 1.03, 1.05, 0.95, "减半或换仓"),
    }
    for code, (label, lo, hi, stop, action) in plan.items():
        nav = fund_data.get(code, (None, None, ""))[0]
        if nav:
            lines.append(
                f"<span style='color:#e60000;'>🔴 {label}｜最新净值{nav:.4f}｜"
                f"反弹{nav*lo:.2f}-{nav*hi:.2f} {action}；跌破{nav*stop:.2f}止损。</span><br>"
            )

    gold_nav = fund_data.get("000217", (None, None, ""))[0]
    if gold_nav:
        lines.append(
            f"<span style='color:#e60000;'>🟢 华安黄金ETF联接C 000217｜最新净值{gold_nav:.4f}｜"
            "不加仓，黄金ETF连续3日跌破9.00再分批减至10%以下。</span><br>"
        )
    lines.append(
        "<span style='color:#e60000;'>🟠 永赢025208/华夏008887｜半导体反弹不追高，"
        "等芯片ETF连续2日站稳后再评估；反弹到成本上方且趋势转弱可减1/3。</span><br>"
    )
    lines.append(
        "<span style='color:#e60000;'>🟢 大成红利090010｜防守仓不足20%可小额定投，"
        "每批≤1%总仓；国泰电网023638站稳1.80/1.85/1.90分3批加仓。</span><br>"
    )
    return lines


def build_html(fund_data, quotes):
    date_text = datetime.now(TZ).strftime("%m月%d日")
    lines = [
        "<div style='font-size:16px;line-height:1.7;color:#000000;background:#ffffff;'>",
        f"<b>🧠 盘中AI深度解读 · {date_text} 14:30（云端兜底版）</b><br><br>",
    ]

    lines.append("<b>【发生了什么】</b><br>")
    for name, symbol in (
        ("上证", "sh000001"),
        ("深成", "sz399001"),
        ("创业板", "sz399006"),
        ("科创50", "sh000688"),
        ("沪深300", "sh000300"),
    ):
        q = quotes.get(symbol)
        if q:
            lines.append(f"{name}{q['price']:.2f} {_fmt_chg(q['chg'])}｜")
    lines[-1] = lines[-1].rstrip("｜") + "<br>"

    moves = []
    for sector, symbol in MAJOR_ETFS:
        q = quotes.get(symbol)
        if q:
            moves.append((sector, q.get("chg"), q.get("price")))
    moves = [m for m in moves if m[1] is not None]
    moves.sort(key=lambda x: x[1], reverse=True)
    if moves:
        top = "、".join(f"{s}{_fmt_chg(c)}" for s, c, _ in moves[:3])
        bottom = "、".join(f"{s}{_fmt_chg(c)}" for s, c, _ in moves[-3:])
        lines.append(f"领涨：{top}<br>")
        lines.append(f"领跌：{bottom}<br>")

    lines.append("<br><b>【为什么】</b><br>")
    if moves:
        top_sectors = {s for s, _, _ in moves[:3]}
        bottom_sectors = {s for s, _, _ in moves[-3:]}
        tech = {"半导体", "机器人/AI", "通信/AI算力", "港股"}
        defense = {"黄金", "红利", "军工", "银行"}
        if top_sectors & tech:
            lines.append("1️⃣ 资金重新回流科技成长，算力/芯片方向成为主要进攻主线。<br>")
        if top_sectors & defense:
            lines.append("1️⃣ 防守与避险方向走强，说明资金优先控制回撤。<br>")
        if bottom_sectors & tech:
            lines.append("2️⃣ 科技高位方向出现兑现，短线追涨风险上升。<br>")
        if bottom_sectors & defense:
            lines.append("2️⃣ 防守方向被抽血，资金转向更高弹性的方向。<br>")
    news = _recent_news()
    if news:
        lines.append("3️⃣ 今日新闻线索：" + "；".join(news[:3]) + "。<br>")

    lines.append("<br><b>【对持仓的影响】</b><br>")
    for code, short, sector in cfr.FUNDS:
        nav, nav_chg, nav_date = fund_data.get(code, (None, None, ""))
        symbol = SECTOR_ETF.get(sector)
        etf_chg = quotes.get(symbol, {}).get("chg") if symbol else None
        if etf_chg is None:
            estimate = "预计震荡"
        elif etf_chg >= 1.5:
            estimate = "预计上涨"
        elif etf_chg <= -1.5:
            estimate = "预计下跌"
        else:
            estimate = "预计小幅波动"
        if nav is None:
            lines.append(f"{short}｜{sector}｜净值数据获取失败｜{estimate}<br>")
        else:
            date_short = nav_date[5:].replace("-", "/") if nav_date else "-"
            lines.append(
                f"{short}｜{sector}｜{nav:.4f}（{date_short}）｜"
                f"{_fmt_chg(nav_chg)}｜今日ETF{_fmt_chg(etf_chg)}｜{estimate}<br>"
            )

    lines.append("<br><b>【什么时候操作】</b><br>")
    lines.append("14:30-15:00是主要操作窗口；14:30前不追涨，15:00后不追跌。<br>")
    lines.append("科技方向看明天能否连续站稳关键位；黄金看9.00是否连续失守。<br>")

    lines.append("<br><b>【操作方式】</b><br>")
    lines.extend(_operation_lines(fund_data, quotes))

    lines.append("<br><b>【可建仓方向】</b><br>")
    lines.append("通信/AI算力：等515880连续2日站稳0.68后分3批，每批≤2%。<br>")
    lines.append("医药001344：等159938重新站稳0.69后分2批，每批≤1.5%。<br>")
    lines.append("红利低波007466：每周定投0.5%-1%，作为防守补充。<br>")
    lines.append("半导体：只用008887等指数基金右侧参与，不追单日大涨。<br>")

    lines.append("<br><b>【风险提示】</b><br>")
    lines.append("科技单日大涨后可能冲高回落；黄金、海外资产受利率与地缘消息扰动较大。<br>")
    lines.append(
        "<span style='color:#555555;font-size:13px;'>云端规则版深度解读，AI分析仅供参考，不构成投资建议。</span><br>"
    )
    lines.append("</div>")
    return "".join(lines)


def _market_context(fund_data, quotes):
    parts = []
    for name, symbol in (
        ("上证", "sh000001"),
        ("深成", "sz399001"),
        ("创业板", "sz399006"),
        ("科创50", "sh000688"),
        ("沪深300", "sh000300"),
    ):
        q = quotes.get(symbol)
        if q:
            parts.append(f"{name} {q['price']:.2f} {q['chg']:+.2f}%")
    lines = ["指数：" + "；".join(parts)]

    sector_lines = []
    for sector, symbol in MAJOR_ETFS:
        q = quotes.get(symbol)
        if q:
            sector_lines.append(f"{sector} {q['chg']:+.2f}%")
    lines.append("板块ETF：" + "；".join(sector_lines))

    fund_lines = []
    for code, short, sector in cfr.FUNDS:
        nav, chg, date = fund_data.get(code, (None, None, ""))
        if nav is None:
            fund_lines.append(f"{short}（{code}，{sector}）：净值获取失败")
        else:
            fund_lines.append(
                f"{short}（{code}，{sector}）：净值{nav:.4f}（{date}），{chg:+.2f}%"
            )
    lines.append("持仓基金：" + "；".join(fund_lines))
    news = _recent_news()
    if news:
        lines.append("今日新闻：" + "；".join(news))
    return "\n".join(lines)


def generate_ai_html(fund_data, quotes):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return build_html(fund_data, quotes)

    date_text = datetime.now(TZ).strftime("%m月%d日")
    context = _market_context(fund_data, quotes)
    prompt = f"""你是我的基金分析助手。请基于下面真实行情与持仓数据，生成一份适合 iPhone 微信阅读的 HTML 深度分析。

硬性要求：
1. 只输出一个 HTML 片段，从 <div 开始到 </div> 结束，不要 Markdown 代码块。
2. 正文纯黑 #000000、字号16px、行高1.7；重点数据/操作/风险用 #e60000 红色；免责声明用 #555555。
3. 标题写：🧠 盘中AI深度解读 · {date_text} 14:30
4. 必须包含这些板块：【发生了什么】【为什么】【对持仓的影响】【什么时候操作】【操作方式】【可建仓方向】【风险提示】。
5. 【为什么】用1-3句简单直白的逻辑，不要空话。
6. 【对持仓的影响】要覆盖下面持仓基金中受影响最大的部分，说明预计方向；当天净值未公布时用ETF/指数估算。
7. 【什么时候操作】写清楚今天14:30-15:00、明天开盘、连续2日确认等具体时间窗口。
8. 【操作方式】必须具体到基金全名+代码、买卖/减仓/止损/止盈、分批次数、每批占总仓位比例、触发净值或ETF点位。
9. 不要承诺收益，不要制造恐慌；结尾加灰色免责声明：AI分析仅供参考，不构成投资建议。

行情与持仓数据：
{context}
"""
    payload = {
        "model": "deepseek-flash",
        "messages": [
            {"role": "system", "content": "你是严谨、克制、面向普通投资者的基金分析助手。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 3500,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        html = data["choices"][0]["message"]["content"].strip()
        html = re.sub(r"^```(?:html)?\s*", "", html)
        html = re.sub(r"\s*```$", "", html)
        if "<div" in html:
            html = html[html.find("<div") :]
        if "</div>" in html:
            html = html[: html.rfind("</div>") + len("</div>")]
        else:
            html += "</div>"
        return html
    except Exception as exc:
        print("AI_ERR", str(exc)[:240], file=sys.stderr)
        return build_html(fund_data, quotes)


def main():
    symbols = sorted(
        set(
            list(SECTOR_ETF.values())
            + list(cfr.ETF_MAP.values())
            + [
                "sh000001",
                "sz399001",
                "sz399006",
                "sh000688",
                "sh000300",
                "sh000905",
                "sh512800",
                "sh512880",
                "sh515880",
                "sz159938",
                "sh562960",
                "sh561380",
                "sz159392",
                "sh511260",
                "sh513030",
            ]
        )
    )
    print("fetching quotes...", file=sys.stderr)
    quotes = cfr.get_quotes(symbols)
    print("fetching fund navs...", file=sys.stderr)
    fund_data = {}
    for code, short, sector in cfr.FUNDS:
        nav, chg, date = cfr.get_fund_nav(code)
        fund_data[code] = (nav, chg, date)
        print(code, short, nav, chg, date, file=sys.stderr)

    html = generate_ai_html(fund_data, quotes)
    REPORTS_DIR.mkdir(exist_ok=True)
    dated = REPORTS_DIR / f"cloud_deep_analysis_{datetime.now(TZ).strftime('%Y%m%d')}.html"
    dated.write_text(html, encoding="utf-8")
    (REPORTS_DIR / "latest_cloud_deep_analysis.html").write_text(html, encoding="utf-8")
    print("SAVED", dated)
    title = f"🧠 盘中AI深度解读 {datetime.now(TZ).strftime('%m月%d日')} 14:30"
    return cfr.send(title, html)


if __name__ == "__main__":
    sys.exit(main())
