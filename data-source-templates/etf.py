"""Fetch current prices for Shanghai or Shenzhen exchange-traded funds."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ETF_CODE_PATTERN = re.compile(r"^\d{6}$")
QUOTE_URL = "https://qt.gtimg.cn/"
REQUEST_HEADERS = {
    "Referer": "https://gu.qq.com/",
    "User-Agent": "Mozilla/5.0 (compatible; SuiShi/1.0)",
}


def _market_symbol(code: Any) -> tuple[str, str]:
    value = str(code or "").strip()
    if not ETF_CODE_PATTERN.fullmatch(value):
        raise ValueError(f"ETF 代码必须是 6 位数字，收到：{value!r}")
    if value.startswith("5"):
        return value, f"sh{value}"
    if value.startswith("1"):
        return value, f"sz{value}"
    raise ValueError(
        f"无法识别 ETF {value} 的交易所（仅支持沪市 5xxxxx、深市 1xxxxx）"
    )


def _parse_quote(code: str, market_symbol: str, content: bytes) -> dict[str, str]:
    text = content.decode("gb18030", errors="replace").strip()
    marker = f'v_{market_symbol}="'
    line = next((row for row in text.splitlines() if row.startswith(marker)), "")
    if not line:
        raise RuntimeError(f"ETF {code} 查询失败：上游没有返回行情")
    fields = line[len(marker) :].removesuffix('";').split("~")
    if len(fields) <= 30 or not fields[3]:
        raise RuntimeError(f"ETF {code} 查询失败：行情字段不完整")
    price = fields[3].strip()
    if float(price) <= 0:
        raise RuntimeError(
            f"ETF {code} 当前没有有效成交价，可能尚未上市或已停牌"
        )
    return {
        "code": code,
        "name": fields[1].strip(),
        "price": price,
        "observed_at": fields[30].strip(),
        "market": market_symbol[:2],
    }


def get_price(code: str) -> dict[str, str]:
    """Return the current/latest traded ETF price."""
    normalized, market_symbol = _market_symbol(code)
    request = Request(
        f"{QUOTE_URL}?{urlencode({'q': market_symbol})}", headers=REQUEST_HEADERS
    )
    with urlopen(request, timeout=15.0) as response:
        content = response.read()
    return _parse_quote(normalized, market_symbol, content)


def fetch(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """SuiShi data-source entrypoint; expects each item to contain ``code``."""
    results = []
    for item in payload.get("items", []):
        quote = get_price(item.get("code"))
        results.append({"asset_id": item["asset_id"], **quote})
    return {"items": results}
