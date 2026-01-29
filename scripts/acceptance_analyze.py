"""
Analyze acceptance_report*.json and cluster failures.

Usage:
  python scripts\\acceptance_analyze.py acceptance_report.sample4.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from typing import Any


def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _classify(r: dict[str, Any]) -> str:
    if r.get("ok") is not True:
        err = r.get("error") or {}
        msg = ""
        if isinstance(err, dict):
            msg = str(err.get("message") or err.get("details") or "")
        else:
            msg = str(err)
        msg_l = msg.lower()
        if "captcha" in msg_l or "403" in msg_l:
            return "blocked_captcha_403"
        if "504" in msg_l or "timeout" in msg_l:
            return "gateway_timeout_504"
        if "520" in msg_l:
            return "server_error_520"
        return "tool_error_other"

    brief = r.get("output_brief") if isinstance(r.get("output_brief"), dict) else {}
    status = str(brief.get("status") or "").strip()
    if status.lower() == "timeout":
        return "task_timeout"
    if status.lower() == "failed":
        return "task_failed"
    if status:
        # Ready/Success etc handled in success bucket by caller
        return f"task_status_{status}"
    return "unknown"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts\\acceptance_analyze.py <report.json>")
        return 2
    path = sys.argv[1]
    rep = _load(path)
    results = rep.get("results") if isinstance(rep.get("results"), list) else []

    buckets = Counter()
    by_group = defaultdict(Counter)
    top_examples = defaultdict(list)

    for r in results:
        if not isinstance(r, dict):
            continue
        brief = r.get("output_brief") if isinstance(r.get("output_brief"), dict) else {}
        status = str(brief.get("status") or "").strip()
        dl = brief.get("download_url")
        dv = r.get("download_verify")
        succeeded = status in {"Ready", "Success", "Succeeded", "Task Succeeded"}
        dl_ok = isinstance(dv, dict) and dv.get("ok") is True
        group = str(r.get("group") or "other")

        if succeeded and dl and dl_ok:
            buckets["success"] += 1
            by_group[group]["success"] += 1
            continue

        c = _classify(r)
        buckets[c] += 1
        by_group[group][c] += 1
        if len(top_examples[c]) < 6:
            top_examples[c].append(
                {
                    "tool_key": r.get("tool_key"),
                    "status": status,
                    "spider_id": r.get("spider_id"),
                    "spider_name": r.get("spider_name"),
                    "params": r.get("params"),
                    "error": r.get("error"),
                    "download_verify": dv,
                }
            )

    print("== Summary ==")
    for k, v in buckets.most_common():
        print(f"- {k}: {v}")
    print("\n== By group ==")
    for g, c in sorted(by_group.items(), key=lambda kv: sum(kv[1].values()), reverse=True):
        total = sum(c.values())
        top = ", ".join([f"{k}:{v}" for k, v in c.most_common(5)])
        print(f"- {g}: total={total} {top}")
    print("\n== Examples ==")
    for k, exs in top_examples.items():
        print(f"\n[{k}]")
        for e in exs:
            print("-", e["tool_key"], "status=", e["status"], "params=", e["params"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

