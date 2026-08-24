#!/usr/bin/env python3
"""云端实时基金晨报（规则版）：GitHub Actions 每天15:00运行，不依赖本机。"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"

FUNDS = [
    ("000217", "华安黄金", "黄金"),
    ("022459", "A500", "宽基"),
    ("025833", "电网·天弘", "电网"),
    ("018044", "纳指·天弘", "纳指"),
    ("025208", "半导体·永赢", "半导体"),
    ("012920", "全球成长", "海外"),
    ("539001", "纳指·建信", "纳指"),
    ("021895", "机器人", "机器人"),
    ("160125", "港股", "港股"),
    ("457001", "亚洲", "亚洲"),
    ("006503", "集成电路·财通", "半导体"),
    ("019058", "绿电", "绿电"),
    ("013188", "新能源", "新能源"),
    ("090010", "红利", "红利"),
    ("024688", "低空", "低空"),
    ("100050", "全球债", "债券"),
    ("002251", "军工", "军工"),
    ("011035", "稀土", "稀土"),
    ("019450", "欧洲", "欧洲"),
    ("023638", "电网·国泰", "电网"),
    ("008887", "半导体·华夏", "半导体"),
]

ETF_MAP = {
    "黄金": "sh518880",
    "宽基": "sz159338",
    "纳指": "sh513100",
    "半导体": "sh512760",
    "海外": "sh513500",
    "机器人": "sz159819",
    "港股": "sh513050",
    "亚洲": "sh513050",
    "新能源": "sh515790",
    "红利": "sh515180",
    "军工": "sh512660",
    "稀土": "sh516780",
    "通信": "sh515880",
    "医药": "sz159938",
}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def get_quotes(symbols):
    if not symbols:
        return {}
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


def get_fund_nav(code):
    url = (
        "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNBasicInformation"
        f"?FCODE={code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0"
    )
    try:
        data = json.loads(http_get(url))
        d = data.get("Datas") or {}
        nav = float(d.get("DWJZ") or 0)
        date = d.get("FSRQ", "") or d.get("NAVDATE", "")
        chg = float(d.get("RZDF") or 0)
        if nav > 0:
            return nav, chg, date
    except Exception:
        pass
    # fallback: pingzhongdata
    try:
        text = http_get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")
        m = re.search(r"var Data_netWorthTrend = (\[.*?\]);", text)
        rows = json.loads(m.group(1))
        last, prev = rows[-1], rows[-2]
        nav = float(last["y"])
        chg = (last["y"] / prev["y"] - 1) * 100
        date = datetime.fromtimestamp(last["x"] / 1000).strftime("%Y-%m-%d")
        return nav, chg, date
    except Exception:
        return None, None, ""


def red_span(value, bold=False):
    if bold:
        return f'<span style="color:#e60000;font-weight:bold;">{value}</span>'
    return f'<span style="color:#e60000;">{value}</span>'


def fmt_chg(chg, bold_if_ge=5):
    text = f"{chg:+.2f}%"
    if chg >= 3 or chg <= -3:
        return red_span(text, bold=abs(chg) >= bold_if_ge)
    return text


def sector_direction(sector, chg):
    if chg is None:
        return "震荡"
    if sector in ("半导体", "机器人", "军工", "稀土"):
        if chg >= 1:
            return "震荡偏强"
        if chg <= -1:
            return "偏弱，等企稳"
        return "震荡"
    if sector == "黄金":
        return "偏强" if chg >= 1 else "震荡"
    if sector in ("纳指", "海外", "港股"):
        return "震荡偏弱" if chg < 0 else "震荡"
    if sector == "红利":
        return "偏强" if chg >= 0 else "震荡"
    if sector == "医药":
        return "回调观望" if chg < 0 else "偏强"
    return "震荡"


def build_html(fund_data, quotes, indices):
    now = datetime.now(TZ).strftime("%Y年%m月%d日")
    lines = [
        "<div style='font-size:16px;line-height:1.7;color:#000000;'>",
        f"<b>📊 基金晨报（云端实时）· {now}</b><br><br>",
        "<b>【今日市场】</b><br>",
    ]
    idx_parts = []
    for name, sym in (("上证", "sh000001"), ("深成", "sz399001"), ("创业板", "sz399006")):
        q = quotes.get(sym)
        if q:
            idx_parts.append(f"{name}{q['price']:.2f} {fmt_chg(q['chg'])}")
    if idx_parts:
        lines.append("｜".join(idx_parts) + "<br>")
    lines.append("<br><b>【持仓总览】</b><br>")
    lines.append("现金｜余额宝｜无净值｜—<br>")
    for code, short, sector in FUNDS:
        nav, chg, date = fund_data.get(code, (None, None, ""))
        if nav is None:
            lines.append(f"{short}｜{sector}｜数据获取失败<br>")
            continue
        etf_sym = ETF_MAP.get(sector)
        etf_chg = quotes.get(etf_sym, {}).get("chg") if etf_sym else None
        today = fmt_chg(etf_chg) if etf_chg is not None else "—"
        date_short = date[5:].replace("-", "/")
        lines.append(
            f"{short}｜{sector}｜{nav:.4f}（{date_short}）｜{fmt_chg(chg)}｜今日{today}<br>"
        )

    lines.append("<br><b>【明日方向】</b><br>")
    for sector in ("黄金", "宽基", "电网", "半导体", "机器人", "红利", "纳指", "港股", "军工", "稀土", "新能源"):
        etf_sym = ETF_MAP.get(sector)
        chg = quotes.get(etf_sym, {}).get("chg") if etf_sym else None
        lines.append(f"{sector}：{sector_direction(sector, chg)}<br>")
    lines.append("医药：今日回调则观望，159938重新站稳0.69再建仓<br>")

    lines.append("<br><b>【操作计划】</b><br>")
    plan_funds = {
        "006503": ("财通集成电路C 006503", 1.05, 1.08, 0.95, "换华夏008887或减半"),
        "024688": ("富国通航024688", 1.03, 1.05, 0.93, "清仓"),
        "011035": ("嘉实稀土011035", 1.05, 1.08, 0.95, "减半"),
        "160125": ("南方香港160125", 1.03, 1.05, 0.95, "减半或换118001"),
    }
    for code, (label, lo, hi, stop, action) in plan_funds.items():
        nav = fund_data.get(code, (None,))[0]
        if nav:
            lines.append(
                f"<span style='color:#e60000;'>🔴 {label}：反弹至{nav*lo:.2f}-{nav*hi:.2f}减仓/换仓；跌破{nav*stop:.2f}止损</span><br>"
            )
    tp = [
        ("457001", "国富亚洲457001", 3.00),
        ("019450", "摩根欧洲019450", 1.90),
        ("012920", "全球成长012920", 3.90),
    ]
    for code, label, level in tp:
        nav = fund_data.get(code, (None,))[0]
        if nav and nav >= level:
            lines.append(f"<span style='color:#e60000;'>🟠 {label}已到{level}，可止盈1/3</span><br>")
    lines.append("🟢 加仓：国泰电网023638站稳1.80/1.85/1.90分3批（每批≤2%）；天弘025833站稳1.20后分批；大成红利090010每周五定投0.5%-1%<br>")
    lines.append("🟢 建仓：国泰通信007818等515880连续2日站稳0.68后分3批；医药001344等159938重新站稳0.69后分2批<br>")
    lines.append("🟢 黄金不加；518880连续3日跌破9.00减至10%以下；纳指018044/539001反弹后合并<br>")

    lines.append("<br><b>【操作提示】</b><br>")
    lines.append("<span style='color:#e60000;'>🔴 财通006503反弹换仓或减半</span><br>")
    lines.append("<span style='color:#e60000;'>🔴 富国通航024688、嘉实稀土011035反弹卖出</span><br>")
    lines.append("<span style='color:#e60000;'>🟢 国泰电网023638回调分批；大成红利090010定投</span><br>")

    lines.append("<br><b>【新机会扫描】</b><br>")
    lines.append("1️⃣ 通信设备/AI算力：国泰通信设备ETF联接C 007818｜515880站稳0.68后分3批，每批≤2%<br>")
    lines.append("2️⃣ 红利低波：华泰柏瑞红利低波007466｜每周定投，目标5-10%<br>")
    lines.append("3️⃣ 创新药/医药：易方达医药ETF联接A 001344｜159938重新站稳0.69再分2批，每批≤1.5%<br>")
    lines.append("<span style='color:#555555;font-size:13px;'>云端规则版：数据与规则自动生成，非AI深度分析。不构成投资建议。</span>")
    lines.append("</div>")
    return "".join(lines)


def send(title, content):
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


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    print("fetching quotes...", file=sys.stderr)
    all_symbols = list(ETF_MAP.values()) + ["sh000001", "sz399001", "sz399006", "sh513500", "sh513050"]
    quotes = get_quotes(sorted(set(all_symbols)))
    print("fetching fund navs...", file=sys.stderr)
    fund_data = {}
    for code, short, sector in FUNDS:
        nav, chg, date = get_fund_nav(code)
        fund_data[code] = (nav, chg, date)
        print(code, short, nav, chg, date, file=sys.stderr)
    html = build_html(fund_data, quotes, {})
    if dry_run:
        print(html)
        sys.exit(0)
    title = f"📊 基金晨报（云端实时）· {datetime.now(TZ).strftime('%m月%d日')}"
    try:
        REPORTS_DIR.mkdir(exist_ok=True)
        dated = REPORTS_DIR / f"fund_report_{datetime.now(TZ).strftime('%Y%m%d')}.html"
        dated.write_text(html, encoding="utf-8")
        (REPORTS_DIR / "latest.html").write_text(html, encoding="utf-8")
        print("SAVED", dated)
    except Exception as exc:
        print("SAVE_ERR", exc)
    sys.exit(send(title, html))
