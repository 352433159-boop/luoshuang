#!/usr/bin/env python3
"""云端补发：读取 reports/latest.html 并推送到微信（PushPlus）。"""

import argparse
import glob
import json
import os
import sys
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def find_latest_report():
    latest = REPO_ROOT / "reports" / "latest.html"
    if latest.exists():
        return latest
    matches = sorted(glob.glob(str(REPO_ROOT / "reports" / "fund_report_*.html")))
    if matches:
        return Path(matches[-1])
    return None


def send(title, content, dry_run=False):
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        print("NO_TOKEN")
        return 2
    payload = json.dumps(
        {"token": token, "title": title, "content": content, "template": "html"}
    ).encode("utf-8")
    if dry_run:
        print("DRY_RUN_OK", title, len(content))
        return 0
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", default="📊 基金晨报（云端补发）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = find_latest_report()
    if report is None:
        fallback = (
            "<div style='font-size:16px;color:#000;'>"
            "⚠️ 云端补发任务未找到昨日基金晨报文件。<br>"
            "请检查本地15:00任务是否成功生成并推送 reports/latest.html。"
            "</div>"
        )
        sys.exit(send(args.title, fallback, args.dry_run))

    content = report.read_text(encoding="utf-8")
    sys.exit(send(args.title, content, args.dry_run))
