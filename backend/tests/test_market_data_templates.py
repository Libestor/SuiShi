from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "data-source-templates"


class FakeResponse:
    def __init__(self, *, payload=None, content: bytes = b"") -> None:
        self._payload = payload
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        if self._payload is not None:
            import json

            return json.dumps(self._payload).encode("utf-8")
        return self.content


def load_template(name: str) -> ModuleType:
    path = TEMPLATE_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_template_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_off_exchange_fund_returns_latest_unit_nav(monkeypatch) -> None:
    module = load_template("off_exchange_fund")
    payload = {
        "ErrCode": 0,
        "Data": {"LSJZList": [{"FSRQ": "2026-08-11", "DWJZ": "1.3280"}]},
    }
    monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse(payload=payload))

    result = module.fetch({"items": [{"asset_id": "fund-1", "code": "000001"}]})

    assert result == {
        "items": [
            {
                "asset_id": "fund-1",
                "code": "000001",
                "price": "1.3280",
                "price_date": "2026-08-11",
            }
        ]
    }


@pytest.mark.parametrize("template_name,code,symbol", [
    ("etf", "510300", "sh510300"),
    ("etf", "159919", "sz159919"),
    ("stock", "600519", "sh600519"),
    ("stock", "000001", "sz000001"),
    ("stock", "920001", "bj920001"),
])
def test_exchange_quote_templates_infer_market_and_parse_price(
    monkeypatch, template_name: str, code: str, symbol: str
) -> None:
    module = load_template(template_name)
    fields = ["1", "测试标的", code, "12.340"] + [""] * 26 + ["20260811150000"]
    content = f'v_{symbol}="{"~".join(fields)}";'.encode("gb18030")
    calls = []

    def fake_open(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse(content=content)

    monkeypatch.setattr(module, "urlopen", fake_open)
    result = module.fetch({"items": [{"asset_id": "asset-1", "code": code}]})

    assert calls[0][0][0].full_url.endswith(f"?q={symbol}")
    assert result["items"][0] == {
        "asset_id": "asset-1",
        "code": code,
        "name": "测试标的",
        "price": "12.340",
        "observed_at": "20260811150000",
        "market": symbol[:2],
    }


@pytest.mark.parametrize("template_name", ["off_exchange_fund", "etf", "stock"])
def test_templates_reject_non_six_digit_codes(template_name: str) -> None:
    module = load_template(template_name)
    with pytest.raises(ValueError, match="6 位数字"):
        module.get_price("123")
