"""Fetch the latest disclosed unit NAV for an off-exchange Chinese fund."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FUND_CODE_PATTERN = re.compile(r"^\d{6}$")
FUND_NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://fundf10.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (compatible; SuiShi/1.0)",
}


def _normalize_code(code: Any) -> str:
    value = str(code or "").strip()
    if not FUND_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"场外基金代码必须是 6 位数字，收到：{value!r}")
    return value


def get_price(code: str) -> dict[str, str]:
    """Return the fund's latest disclosed unit NAV and its valuation date."""
    fund_code = _normalize_code(code)
    query = urlencode({"fundCode": fund_code, "pageIndex": 1, "pageSize": 1})
    request = Request(f"{FUND_NAV_URL}?{query}", headers=REQUEST_HEADERS)
    with urlopen(request, timeout=15.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = (payload.get("Data") or {}).get("LSJZList") or []
    if payload.get("ErrCode") != 0 or not rows:
        message = payload.get("ErrMsg") or "上游没有返回净值"
        raise RuntimeError(f"基金 {fund_code} 查询失败：{message}")

    latest = rows[0]
    price = str(latest.get("DWJZ") or "").strip()
    if not price or float(price) <= 0:
        raise RuntimeError(f"基金 {fund_code} 没有有效的最新单位净值")
    return {
        "code": fund_code,
        "price": price,
        "price_date": str(latest.get("FSRQ") or ""),
    }


def fetch(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """SuiShi data-source entrypoint; expects each item to contain ``code``."""
    results = []
    for item in payload.get("items", []):
        quote = get_price(item.get("code"))
        results.append({"asset_id": item["asset_id"], **quote})
    return {"items": results}
