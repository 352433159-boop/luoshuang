#!/usr/bin/env python3
"""美国市场风险监控：信用、波动率、利率、银行压力触发时推送微信。"""

import csv
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
STATE_PATH = REPORTS_DIR / "us_risk_state.json"
TZ = timezone(timedelta(hours=8))

SIGNAL_META = {
    "标普500熊市回撤": {
        "cause": "估值偏高、利率高企、盈利预期下修或信用风险升温，导致资金系统性撤离股票。",
        "result": "财富效应逆转、消费和企业信心走弱，可能把股市下跌传导成经济衰退；若信用市场同时恶化，可能演变为金融危机。",
        "watch": "标普500能否止跌、信用利差是否继续走阔、就业和消费数据是否恶化。",
    },
    "标普500技术回调": {
        "cause": "前期涨幅过大、估值偏高、市场对利率或盈利预期重新定价。",
        "result": "高估值板块回撤、波动率上升；如果信用市场稳定，通常只是10%-20%级别的调整，不一定是危机。",
        "watch": "VIX、信用利差、区域银行和小盘股是否同步走弱。",
    },
    "VIX恐慌": {
        "cause": "市场对政策、信用、地缘或流动性风险集中定价，期权对冲和波动率目标基金减仓放大波动。",
        "result": "高beta科技股快速回撤、流动性变差，可能触发程序化卖出；若持续高于30且信用利差走阔，可能升级为系统性风险。",
        "watch": "VIX是否连续高于30、信用利差、美元资金市场和银行股。",
    },
    "VIX升温": {
        "cause": "不确定性上升，投资者开始增加保护性对冲。",
        "result": "市场波动加大，科技和杠杆资金承压；目前更可能是阶段性调整，而不是危机。",
        "watch": "VIX能否回落，还是继续升向30以上。",
    },
    "纳指高位回撤": {
        "cause": "AI和科技股估值高、筹码拥挤、对利率敏感；一旦盈利或资本开支预期变化，容易集中止盈。",
        "result": "全球科技股和AI供应链承压，可能拖累标普500和风险偏好；如果AI资本开支大幅下修，跌幅可能扩大。",
        "watch": "英伟达指引、微软/谷歌/Meta/亚马逊资本开支、半导体指数和市场宽度。",
    },
    "区域银行压力": {
        "cause": "高利率下商业地产贷款、存款成本和债券浮亏压力较大，区域银行对商业地产暴露更高。",
        "result": "若存款流出或商业地产违约上升，可能引发中小银行危机、信贷收缩，并冲击商业地产和中小企业；是否演变成系统性危机，取决于风险是否蔓延到大银行和存款保险/流动性工具是否介入。",
        "watch": "KRE是否继续跑输、商业地产违约率、银行CDS、存款流出和美联储流动性工具。",
    },
    "高收益债相对走弱": {
        "cause": "风险偏好下降，投资者开始要求更高的信用风险补偿。",
        "result": "低评级企业融资成本上升，再融资和违约压力增加；若持续恶化，可能从股市调整升级为信用收缩。",
        "watch": "高收益债利差、违约率、新债发行是否冻结、HYG/LQD比值。",
    },
    "高收益债利差警戒": {
        "cause": "高利率和经济放缓预期使低评级企业违约风险上升。",
        "result": "企业融资成本大幅上升、违约增加、信用市场收缩；若突破500bp并继续走阔，金融危机概率会明显上升。",
        "watch": "HY OAS是否继续上升、违约率、新发市场、银行和私人信贷。",
    },
    "高收益债利差走阔": {
        "cause": "经济增长预期转弱或信用事件出现，市场要求更高风险溢价。",
        "result": "高杠杆企业再融资困难，可能引发评级下调和违约；如果扩散到投资级和银行，会升级为系统性风险。",
        "watch": "利差走阔速度、违约率、区域银行和私人信贷。",
    },
    "投资级信用利差走阔": {
        "cause": "利率高企、财政压力或信用事件导致投资者要求更高补偿。",
        "result": "优质企业融资成本上升，资本开支和回购可能放缓，股市估值承压。",
        "watch": "投资级利差、国债拍卖、企业债发行和银行资产负债表。",
    },
    "美债利率冲击": {
        "cause": "通胀、财政赤字、国债供给或期限溢价上升，推动长端利率快速上行。",
        "result": "股票估值压缩、房地产和高负债企业承压、美元走强、全球流动性收紧；若利率继续突破关键位，可能引发跨资产抛售。",
        "watch": "10年/30年美债收益率、国债拍卖尾部、期限溢价和美元指数。",
    },
    "美元资金市场压力": {
        "cause": "银行准备金、季末、国债发行或回购抵押品压力导致美元短期融资紧张。",
        "result": "融资利率飙升，杠杆基金和银行流动性承压，可能迫使央行提供流动性；这是系统性危机的重要前兆。",
        "watch": "SOFR-IORB、回购利率、FRA-OIS、银行CDS和美联储流动性工具。",
    },
    "美元资金面偏紧": {
        "cause": "短期资金供需失衡，市场对美元流动性开始谨慎。",
        "result": "风险资产波动加大，套息交易和杠杆资金可能被动减仓。",
        "watch": "SOFR-IORB是否继续上升、回购市场和美联储表态。",
    },
}


def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def yahoo_series(ticker, range_="1y"):
    encoded = urllib.parse.quote(ticker, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        f"?range={range_}&interval=1d"
    )
    data = json.loads(fetch_text(url))
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError("empty yahoo result")
    result = result[0]
    timestamps = result.get("timestamp") or []
    closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    series = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        series.append((int(ts), float(close)))
    if not series:
        raise ValueError("empty yahoo series")
    return series


def stooq_series(symbol):
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    rows = list(csv.reader(io.StringIO(fetch_text(url))))
    series = []
    for row in rows[1:]:
        if len(row) < 6:
            continue
        try:
            date = datetime.strptime(row[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            series.append((int(date.timestamp()), float(row[4])))
        except Exception:
            continue
    if not series:
        raise ValueError("empty stooq series")
    return series


def fred_series(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    rows = list(csv.reader(io.StringIO(fetch_text(url))))
    series = []
    for row in rows[1:]:
        if len(row) < 2 or row[1] in ("", "."):
            continue
        try:
            date = datetime.strptime(row[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            series.append((int(date.timestamp()), float(row[1])))
        except Exception:
            continue
    if not series:
        raise ValueError("empty fred series")
    return series


def load_series(ticker, stooq_symbol=None):
    try:
        return yahoo_series(ticker)
    except Exception:
        if stooq_symbol:
            try:
                return stooq_series(stooq_symbol)
            except Exception:
                pass
    return []


def ret(series, days):
    if len(series) <= days:
        return None
    return (series[-1][1] / series[-1 - days][1] - 1) * 100


def abs_change(series, days):
    if len(series) <= days:
        return None
    return series[-1][1] - series[-1 - days][1]


def drawdown(series, days=252):
    values = [v for _, v in series[-days:]]
    if not values:
        return None
    peak = max(values)
    return (values[-1] / peak - 1) * 100


def get_push_token():
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if token:
        return token
    try:
        return (Path.home() / ".config" / "pushplus" / "token").read_text().strip()
    except Exception:
        return ""


def push(title, html):
    token = get_push_token()
    if not token:
        print("NO_TOKEN")
        return 2
    payload = json.dumps(
        {"token": token, "title": title, "content": html, "template": "html"}
    ).encode()
    req = urllib.request.Request(
        "https://www.pushplus.plus/send",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        if data.get("code") == 200:
            print("PUSH_OK", data.get("data", ""))
            return 0
        print("PUSH_FAIL", json.dumps(data, ensure_ascii=False))
        return 1
    except Exception as exc:
        print("PUSH_ERR", str(exc)[:200])
        return 1


def collect_signals():
    signals = []

    spy = load_series("SPY", "spy.us")
    qqq = load_series("QQQ", "qqq.us")
    kre = load_series("KRE", "kre.us")
    hyg = load_series("HYG", "hyg.us")
    lqd = load_series("LQD", "lqd.us")
    vix = load_series("^VIX", "^vix")
    tnx = load_series("^TNX")

    if not tnx:
        try:
            tnx = fred_series("DGS10")
        except Exception:
            tnx = []

    spy_dd = drawdown(spy)
    if spy_dd is not None:
        if spy_dd <= -20:
            signals.append(("high", "标普500熊市回撤", f"SPY距一年高点 {spy_dd:.1f}%"))
        elif spy_dd <= -10:
            signals.append(("warn", "标普500技术回调", f"SPY距一年高点 {spy_dd:.1f}%"))

    vix_now = vix[-1][1] if vix else None
    if vix_now is not None:
        if vix_now >= 30:
            signals.append(("high", "VIX恐慌", f"VIX {vix_now:.1f}，已进入高波动区"))
        elif vix_now >= 25:
            signals.append(("warn", "VIX升温", f"VIX {vix_now:.1f}"))

    if qqq:
        qqq_dd = drawdown(qqq)
        if qqq_dd is not None and qqq_dd <= -15:
            signals.append(("warn", "纳指高位回撤", f"QQQ距一年高点 {qqq_dd:.1f}%"))

    if kre and spy:
        kre_rel = ret(kre, 20) - ret(spy, 20)
        kre_dd = drawdown(kre)
        if kre_rel <= -8 or (kre_dd is not None and kre_dd <= -20):
            signals.append(
                (
                    "warn",
                    "区域银行压力",
                    f"KRE近20日相对SPY {kre_rel:+.1f}%，距高点 {kre_dd:.1f}%",
                )
            )

    if hyg and lqd:
        ratio_series = [(ts, h / l) for (ts, h), (_, l) in zip(hyg, lqd) if l]
        ratio_change = ret(ratio_series, 20)
        if ratio_change is not None and ratio_change <= -2:
            signals.append(
                (
                    "warn",
                    "高收益债相对走弱",
                    f"HYG/LQD近20日 {ratio_change:+.2f}%，信用风险升温",
                )
            )

    try:
        hy_oas = fred_series("BAMLH0A0HYM2")
        hy_now = hy_oas[-1][1]
        hy_change = abs_change(hy_oas, 20)
        if hy_now >= 5:
            signals.append(("high", "高收益债利差警戒", f"HY OAS {hy_now:.2f}%"))
        elif hy_change is not None and hy_change >= 1:
            signals.append(("warn", "高收益债利差走阔", f"20日 +{hy_change:.2f}%"))
    except Exception:
        pass

    try:
        ig_oas = fred_series("BAMLC0A0CM")
        ig_now = ig_oas[-1][1]
        if ig_now >= 1.5:
            signals.append(("warn", "投资级信用利差走阔", f"IG OAS {ig_now:.2f}%"))
    except Exception:
        pass

    tnx_now = tnx[-1][1] if tnx else None
    if tnx_now is not None:
        if tnx_now >= 5.5:
            signals.append(("warn", "美债利率冲击", f"10年期收益率 {tnx_now:.2f}%"))

    try:
        sofr = fred_series("SOFR")
        iorb = fred_series("IORB")
        spread = sofr[-1][1] - iorb[-1][1]
        if spread >= 0.25:
            signals.append(("high", "美元资金市场压力", f"SOFR-IORB {spread:.2f}%"))
        elif spread >= 0.1:
            signals.append(("warn", "美元资金面偏紧", f"SOFR-IORB {spread:.2f}%"))
    except Exception:
        pass

    values = {
        "SPY": spy[-1][1] if spy else None,
        "SPY_DD": spy_dd,
        "QQQ": qqq[-1][1] if qqq else None,
        "VIX": vix_now,
        "KRE": kre[-1][1] if kre else None,
        "HYG": hyg[-1][1] if hyg else None,
        "LQD": lqd[-1][1] if lqd else None,
        "US10Y": tnx_now,
    }
    return signals, values


def build_html(signals, values, test=False):
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    title = "🧪 美国市场风险监控测试" if test else "🚨 美国市场风险信号"
    lines = [
        "<div style='font-size:16px;line-height:1.7;color:#000000;background:#ffffff;'>",
        f"<b>{title}</b><br>",
        f"<span style='color:#555;'>时间：{now} 北京时间</span><br><br>",
        "<b>【触发信号】</b><br>",
    ]
    if test:
        lines.append("<span style='color:#e60000;'>测试信号：VIX升高 + 信用利差走阔 + 区域银行走弱</span><br>")
    for level, name, detail in signals:
        color = "#e60000" if level == "high" else "#e60000"
        label = "🔴 高风险" if level == "high" else "🟠 警告"
        lines.append(f"<span style='color:{color};'>{label}｜{name}｜{detail}</span><br>")
    lines.append("<br><b>【当前指标】</b><br>")
    for key, value in values.items():
        if value is None:
            continue
        lines.append(f"{key}：{value:.4f}<br>")
    lines.append("<br><b>【背后原因】</b><br>")
    for level, name, detail in signals:
        meta = SIGNAL_META.get(name, {})
        lines.append(f"<b>{name}</b>：{meta.get('cause', '市场风险偏好或流动性出现变化。')}<br>")
    lines.append("<br><b>【可能造成的结果】</b><br>")
    for level, name, detail in signals:
        meta = SIGNAL_META.get(name, {})
        lines.append(f"<b>{name}</b>：{meta.get('result', '可能带来波动放大和风险资产回撤。')}<br>")
    lines.append("<br><b>【接下来重点观察】</b><br>")
    for level, name, detail in signals:
        meta = SIGNAL_META.get(name, {})
        lines.append(f"<b>{name}</b>：{meta.get('watch', '观察信号是否连续出现并扩散。')}<br>")
    lines.append("<br><b>【综合预测】</b><br>")
    if any(level == "high" for level, _, _ in signals):
        lines.append(
            "<span style='color:#e60000;'>高风险：系统性压力正在上升。"
            "未来1-3个月出现10%以上回调概率约60%-70%，20%以上大跌概率约40%-50%，"
            "演变成金融危机的概率约20%-30%。</span><br>"
        )
    else:
        lines.append(
            "<span style='color:#e60000;'>警告：目前更像阶段性/局部调整，尚未构成系统性危机。"
            "未来1-3个月出现10%左右回调概率约50%-60%，20%以上大跌概率约25%-35%，"
            "演变成金融危机的概率约10%-15%；若信用利差、VIX和资金市场同步恶化，概率会迅速上升。</span><br>"
        )
    lines.append("<br><b>【建议动作】</b><br>")
    lines.append("1️⃣ 降低高估值科技/AI和杠杆仓位；<br>")
    lines.append("2️⃣ 增加现金、短债、黄金等防守资产；<br>")
    lines.append("3️⃣ 观察信号是否连续2-3天出现，避免单日假信号；<br>")
    lines.append("4️⃣ 若VIX>30、信用利差快速走阔、区域银行继续大跌，优先控制风险。<br>")
    lines.append(
        "<br><span style='color:#555555;font-size:13px;'>"
        "风险监控，不构成投资建议。</span></div>"
    )
    return "".join(lines)


def main():
    test_mode = "--test" in sys.argv
    dry_run = "--dry-run" in sys.argv
    if test_mode:
        signals = [
            ("high", "VIX恐慌", "VIX 32.0，测试信号"),
            ("warn", "高收益债利差走阔", "HY OAS 20日 +1.20%，测试信号"),
            ("warn", "区域银行压力", "KRE近20日相对SPY -9.5%，测试信号"),
        ]
        values = {"VIX": 32.0, "HY_OAS": 5.2, "KRE_SPY_20D": -9.5}
    else:
        signals, values = collect_signals()
    print("SIGNALS", json.dumps(signals, ensure_ascii=False))
    if dry_run:
        return 0
    if not signals and not test_mode:
        print("NO_SIGNAL")
        return 0

    severity = "high" if any(s[0] == "high" for s in signals) else "warn"
    signal_keys = sorted(name for _, name, _ in signals)
    now = int(time.time())
    state = {}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if not test_mode:
        last_ts = int(state.get("last_alert_ts", 0))
        same = state.get("last_signal_keys") == signal_keys
        last_severity = state.get("last_severity")
        if same and now - last_ts < 6 * 3600 and not (
            severity == "high" and last_severity != "high"
        ):
            print("THROTTLED")
            return 0

    title = "🧪 美国市场风险监控测试" if test_mode else "🚨 美国市场风险信号"
    code = push(title, build_html(signals, values, test=test_mode))
    if code == 0 and not test_mode:
        REPORTS_DIR.mkdir(exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "last_alert_ts": now,
                    "last_signal_keys": signal_keys,
                    "last_severity": severity,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
