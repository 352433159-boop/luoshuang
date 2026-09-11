#!/usr/bin/env python3
"""云端 A股投资者日报：抓取行情、资金流、新闻，调用 DeepSeek 生成并推送。"""

import importlib.util
import json
import os
import re
import sys
import urllib.parse
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


cda = _load_module("cloud_deep_analysis", SCRIPT_DIR / "cloud_deep_analysis.py")
cfr = cda.cfr


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def eastmoney_list(fs, fid="f3", po=1, pz=15, fields="f12,f14,f2,f3,f6,f62"):
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn=1&pz={pz}&po={po}&np=1&fltt=2&invt=2&fid={fid}"
        f"&fs={urllib.parse.quote(fs, safe='+:!,')}&fields={fields}"
    )
    try:
        data = json.loads(http_get(url))
        return (data.get("data") or {}).get("diff") or []
    except Exception:
        return []


def market_flow():
    result = {}
    for name, secid in (("sh", "1.000001"), ("sz", "0.399001")):
        url = (
            "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?"
            f"lmt=1&klt=1&secid={secid}&fields1=f1,f2,f3,f7&"
            "fields2=f51,f52,f53,f54,f55,f56"
        )
        try:
            data = json.loads(http_get(url))
            row = (data.get("data", {}).get("klines") or [""])[0].split(",")
            if len(row) >= 6:
                result[name] = {
                    "main": float(row[1]),
                    "small": float(row[2]),
                    "medium": float(row[3]),
                    "large": float(row[4]),
                    "super": float(row[5]),
                }
        except Exception:
            continue
    return result


def _yi(value):
    return value / 100000000 if value is not None else None


def _flow_text(name, rows):
    parts = []
    for row in rows[:6]:
        value = row.get("f62")
        if value is None:
            continue
        parts.append(f"{row.get('f14')} {value/1e8:+.2f}亿")
    return f"{name}：" + "；".join(parts) if parts else f"{name}：数据获取失败"


def build_context():
    quotes = cfr.get_quotes(
        [
            "sh000001",
            "sz399001",
            "sz399006",
            "sh000688",
            "sh000300",
            "sh000905",
            "sh518880",
            "sh512760",
            "sh515880",
            "sh513050",
            "sh515180",
            "sh512660",
            "sh516780",
            "sh512400",
            "sh512800",
            "sh512880",
        ]
    )
    context = [
        cda._market_context({}, quotes),
    ]

    flow = market_flow()
    if flow:
        sh = flow.get("sh", {})
        sz = flow.get("sz", {})
        total_main = sh.get("main", 0) + sz.get("main", 0)
        total_small = sh.get("small", 0) + sz.get("small", 0)
        context.append(
            "市场资金：两市主力净流入"
            f"{_yi(total_main):+.2f}亿；"
            f"沪市主力{_yi(sh.get('main')):+.2f}亿，深市主力{_yi(sz.get('main')):+.2f}亿；"
            f"小单净流入{_yi(total_small):+.2f}亿。"
        )

    industry_in = eastmoney_list("m:90+t:2+f:!50", "f62", 1, 15)
    industry_out = eastmoney_list("m:90+t:2+f:!50", "f62", 0, 15)
    concept_in = eastmoney_list("m:90+t:3+f:!50", "f62", 1, 15)
    concept_out = eastmoney_list("m:90+t:3+f:!50", "f62", 0, 15)
    stock_in = eastmoney_list(
        "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "f62", 1, 20
    )
    stock_out = eastmoney_list(
        "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "f62", 0, 20
    )
    gainers = eastmoney_list(
        "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "f3", 1, 20
    )
    turnover = eastmoney_list(
        "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", "f6", 1, 20
    )
    context.append(_flow_text("行业净流入", industry_in))
    context.append(_flow_text("行业净流出", industry_out))
    context.append(_flow_text("概念净流入", concept_in))
    context.append(_flow_text("概念净流出", concept_out))
    context.append(_flow_text("个股净流入", stock_in))
    context.append(_flow_text("个股净流出", stock_out))

    gain_text = []
    for row in gainers[:12]:
        gain_text.append(
            f"{row.get('f12')} {row.get('f14')} {row.get('f3'):+.2f}%"
        )
    context.append("涨幅榜：" + "；".join(gain_text))
    turnover_text = []
    for row in turnover[:12]:
        amount = row.get("f6")
        if amount is not None:
            turnover_text.append(f"{row.get('f14')} {amount/1e8:.1f}亿")
    context.append("成交额榜：" + "；".join(turnover_text))

    context.append("今日新闻：" + "；".join(cda._recent_news()))
    return quotes, "\n".join(context)


def call_deepseek(prompt, api_key):
    payload = {
        "model": "deepseek-flash",
        "messages": [
            {"role": "system", "content": "你是严谨的A股投资者日报编辑。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    choice = data["choices"][0]
    print(
        "AI_USAGE",
        choice.get("finish_reason"),
        data.get("usage"),
        file=sys.stderr,
    )
    html = choice["message"]["content"].strip()
    html = re.sub(r"^```(?:html)?\s*", "", html)
    html = re.sub(r"\s*```$", "", html)
    if "<div" in html:
        html = html[html.find("<div") :]
    if "</div>" in html:
        html = html[: html.rfind("</div>") + len("</div>")]
    else:
        html += "</div>"
    return html


def generate_html(context):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    date_text = datetime.now(TZ).strftime("%m月%d日")
    required = [
        "【市场总览】",
        "【市场资金流向】",
        "【重点新闻及影响】",
        "【个股检测与背后逻辑】",
        "【未来方向】",
        "【未来看好的方向/个股】",
        "【新机会与建仓机会】",
        "【操作信息】",
        "【风险提示】",
    ]
    if not api_key:
        return build_fallback(context, required)

    prompt = f"""请根据以下真实数据，生成一份适合微信阅读的A股投资者日报 HTML。

要求：
1. 只输出 HTML 片段，从 <div 开始到 </div> 结束，不要 Markdown 代码块。
2. 正文纯黑 #000000、字号16px、行高1.7；重点数字/操作/风险用 #e60000；免责声明用 #555555。
3. 标题：📊 A股投资者日报 · {date_text}
4. 必须完整包含：{"、".join(required)}。
5. 每个板块1-3句或3-6条短句，务必一次完整输出，不要截断。
6. 个股部分必须写：代码+名称、涨跌、背后逻辑、关注点、操作条件（买点/止损/不追高）。
7. 资金流向必须写：两市主力净流入/流出、行业和个股主要流入流出方向。
8. 最后写：AI分析仅供参考，不构成投资建议。

数据：
{context}
"""
    for attempt in range(2):
        try:
            html = call_deepseek(prompt, api_key)
        except Exception as exc:
            print("AI_ERR", str(exc)[:240], file=sys.stderr)
            break
        missing = [s for s in required if s not in html]
        print("AI_ATTEMPT", attempt + 1, "LEN", len(html), "MISSING", missing, file=sys.stderr)
        if not missing and len(html) >= 2500:
            return html
        prompt += "\n\n重要：必须完整输出全部板块，压缩每部分，不要截断。"
    print("AI_FALLBACK", file=sys.stderr)
    return build_fallback(context, required)


def build_fallback(context, required):
    body = "<br>".join(
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for line in context.splitlines()
    )
    return (
        "<div style='font-size:16px;line-height:1.7;color:#000000;background:#ffffff;'>"
        f"<b>📊 A股投资者日报 · {datetime.now(TZ).strftime('%m月%d日')}</b><br><br>"
        + "".join(f"<b>{section}</b><br>" for section in required)
        + f"<br>{body}<br>"
        "<span style='color:#555555;font-size:13px;'>AI分析仅供参考，不构成投资建议。</span></div>"
    )


def main():
    dry_run = "--dry-run" in sys.argv
    quotes, context = build_context()
    html = generate_html(context)
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "latest_a_share_daily.html").write_text(html, encoding="utf-8")
    dated = REPORTS_DIR / f"a_share_daily_{datetime.now(TZ).strftime('%Y%m%d')}.html"
    dated.write_text(html, encoding="utf-8")
    print("SAVED", dated)
    print("HTML_LEN", len(html))
    if dry_run:
        print(html)
        return 0
    title = f"📊 A股投资者日报 {datetime.now(TZ).strftime('%m月%d日')}"
    return cfr.send(title, html)


if __name__ == "__main__":
    sys.exit(main())
