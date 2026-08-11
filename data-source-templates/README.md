# 行情数据源脚本

这里的三个脚本可直接复制到 SuiShi 的“数据源与自动化”页面：

| 脚本 | 用途 | 支持的代码 |
| --- | --- | --- |
| `off_exchange_fund.py` | 场外基金最新已披露单位净值 | 6 位基金代码 |
| `etf.py` | 沪深场内 ETF 最新成交价 | 沪市 `5xxxxx`、深市 `1xxxxx` |
| `stock.py` | 沪深北股票最新成交价 | 6 位股票代码 |

三个脚本使用相同的数据源配置：

- 入口函数：`fetch`
- 输入映射：`code` → `symbol`
- 输出映射：`unit_price` → `price`
- 依赖包：留空（只使用 Python 标准库）

单项输入示例：

```json
{"items":[{"asset_id":"asset-id","code":"000001"}]}
```

输出示例：

```json
{"items":[{"asset_id":"asset-id","code":"000001","price":"1.3280","price_date":"2026-08-11"}]}
```

也可以在 Python 中调用各脚本的 `get_price("六位代码")`。场外基金返回基金公司最新披露的单位净值，并非盘中估值；ETF 和股票在交易时段返回当前成交价，非交易时段返回最近成交价。
