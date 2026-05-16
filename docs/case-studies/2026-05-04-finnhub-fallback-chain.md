---
title: Finnhub Fallback Chain & the "Lying Comment" Pattern
status: shipped
version: backend@0.15.x
last_updated: 2026-05-04
owner: maintainer
related_paths:
  - backend/src/services/data_manager/
  - backend/src/services/market_data/finnhub.py
---

# Finnhub 集成：fallback 链 + "注释撒谎"模式

> **TL;DR (EN)**: Alpha Vantage's 5-call/minute, 500/day limit could not
> survive a single Deep ReAct run. We added Finnhub as the new primary
> provider, demoted AV to fallback, and kept yfinance as the safety net.
> The architectural decision (put the fallback chain in `DataManager`,
> not in each tool) paid off; along the way we found a "lying comment"
> in the existing AV service that said one thing and did another.
> **TL;DR (中文)**: AV 5/分钟、500/天 撑不住一次 Deep ReAct（31 个 sub-agent
> 工具调用）。引入 Finnhub 作为新 primary、AV 退 fallback、yfinance 兜底；
> fallback 链放在 `DataManager` 而非每个 tool。过程中发现了一处"注释撒谎"
> ——AV service 的注释和实现不一致的潜伏 bug。

> Date: 2026-05-04
> Component: backend/src/services/data_manager + finnhub provider
> Severity: 🟢 中等（功能扩展，零回归；副带修了一个**注释和实现不一致**的潜伏 bug）

## 1. 背景 / Context

项目原本只有 Alpha Vantage 一个数据源（5 调用/分钟、500/天），跑一次 Deep ReAct 一个 financial sub-agent 就用 31 个工具调用，30 秒内必撞限额。需要加一个**真正能撑住**的实时报价 / 新闻 / 内幕交易源。

选型评估后定 Finnhub（60/分、无日限）作为新的 primary，AV 退为 fallback，yfinance 兜底。

## 2. 思考过程 / Reasoning

### 第一个判断：fallback 链放哪里？

有两个候选位置：
- **选项 A**：每个 tool 自己写 try/except 链
- **选项 B**：放进 `DataManager`（已有的数据访问抽象层）

代码探索发现 `AlphaVantageMarketDataService` 上有 `DeprecationWarning("use DataManager")`——架构方向已经定了，AV 工具直接调 service 是历史包袱不是规范。**选 B**：
- 所有 caller（chart API / PCR / insights / 新 tools）一次受益
- 测试一次（mock 三家 service），所有 caller 受益
- 不动现有 13 个 AV 工具

### 第二个判断：tool 命名

候选：
- `get_stock_quote_v2`（通用名 + 版本号）—— 容易跟现有 `get_stock_quote` 撞，agent 不知道选哪个
- `finnhub_quote`（vendor 前缀）—— 暴露实现，但 LLM 看名字就知道"这是个独立来源"，调用语义清晰

选 vendor 前缀。注意：tool 名字暴露 vendor，但**实际数据来源由 fallback 链决定**（finnhub_quote 也可能返回 yfinance 的数据）。这种"名实可能不符"在 PRD 里明确标注，避免未来调试时困惑。

### 第三个判断：Finnhub key 缺失时的行为

两个选项：
- 报错告诉用户"missing key"
- 静默跳过，让 AV 接管

选静默——理由是这个 key 是 optional enhancement，不是 required dependency。报错会污染日志，让用户以为出问题了。代码里加注释明确这是 expected config state。

## 3. 根因 / Root cause（额外发现的预存 bug）

写 `_fetch_quote` 的 fallback 链时，发现原版本是这样的：

```python
async def _fetch_quote(self, symbol: str) -> QuoteData:
    """Internal: Fetch quote from Alpha Vantage."""
    try:
        data = await self._av_service.get_quote(symbol)
        return QuoteData(...)
    except Exception as e:
        logger.error("quote_fetch_failed", symbol=symbol, error=str(e))
        raise DataFetchError(str(e), "alpha_vantage") from e
```

但 `core/config.py` 里 `alpha_vantage_api_key` 字段的注释写：

```python
alpha_vantage_api_key: str = ""  # optional, falls back to yfinance when empty
```

**注释撒谎了。** 实际代码里没有任何 yfinance fallback 分支——AV 失败就直接 raise。这条注释可能是 W7（移除付费源那次重构）时写的意图，但代码实现从未跟上。

如果不是这次跨厂商扩展逼我重读 `_fetch_quote`，这个 bug 可能再潜伏几年——因为 yfinance fallback 的"缺席"是无法通过现有测试发现的（没有"key 为空时 AV 不应该被调用"这种测试）。

## 4. 解决方案 / Fix

### 主要改动
- 新建 `services/finnhub/service.py`：`FinnhubService` async 客户端，3 个端点（`/quote`、`/company-news`、`/stock/insider-transactions`）
- `DataManager.__init__` 增加 optional `finnhub_service` 参数
- `_fetch_quote` 重写为三段 try/except 链：Finnhub → AV → yfinance
- 新增 `get_company_news` / `get_insider_trades`（同一 fallback 模式）
- 3 个 LangChain tool 通过 DataManager 调用（不直接调 service）

### 测试关键决策

写 `test_finnhub_fails_av_succeeds` 时，发现一个陷阱：mock 了 finnhub fail + AV success，断言 `q.price == 281.0`。结果跑出来 `280.14`——这是真的 AAPL 价！

排查后发现：mock AV 返回的 `change_percent: "0.36%"`（带百分号字符串），但 manager 用 `float(...)` 直接转，挂掉。然后 fallback 到 yfinance，**真的去网上拉了** AAPL 实时价。

教训：fallback 测试必须 patch yfinance 让它显式 fail，才能证明 AV 路径真的拿到了 mock 数据，而不是 yfinance 兜底救场。修正后所有 fallback 测试都 `patch.object(DataManager, "_fetch_quote_yfinance", new=AsyncMock(side_effect=AssertionError(...)))`。

### 端到端验证收获

部署后用真 Finnhub key 跑端到端验证，故意把 Finnhub key 填错触发 fallback：

```
[warning] quote_provider_failed provider=finnhub error='HTTP 401'
[warning] quote_provider_failed provider=alpha_vantage error='No quote data'
  AV result: $280.14  (实际 yfinance 救场)
```

AV 也意外失败了！如果只跑单元测试，永远看不到这种"两个上游都坏 yfinance 救场"的真实路径。**真实环境跑一次错误注入比 100 个 mock 测试更能验证 fallback 链。**

## 5. 教训 / Takeaways

1. **不要相信代码注释，特别是 "falls back to X" 这种描述运行时行为的注释。** 注释是开发者意图的快照，代码是实际行为。两者一旦不同步，注释会持续误导所有读者。修代码时如果发现注释撒谎，就地改代码或就地删注释。
2. **架构 deprecation 信号要珍惜。** 看到 `DeprecationWarning("use X instead")` 就直接照着 X 实现新功能——别因为"现有代码也没遵循"就跟着违规。新功能是确立新规范的最好时机。
3. **Mock 测试的最大盲点：fallback 链。** 多层 fallback 测试如果不显式 mock 最后一层（让它 fail），中间层的 bug 会被静默兜底。每个 fallback 测试都应该有"显式禁止下一层被调用"的断言。
4. **Tool 命名暴露 vendor 是有意识的取舍。** 通用名（`get_quote`）让 LLM 没歧义但隐藏实现；vendor 前缀（`finnhub_quote`）暴露实现但语义清晰。后者更适合"我要一个独立来源"的场景，也方便 debug 时定位。
5. **"撞限额时降级"vs"健康时多源验证"是不同需求。** 这次只做了前者（fallback 链）。后者（同时调 3 家然后投票）是另一条路，但延迟和成本都翻 3 倍，目前没必要。
6. **真实错误注入 >>> mock 测试。** 用真 Finnhub key + 故意填错触发的端到端，发现了"AV 也意外挂"这种 mock 永远遇不到的边缘情况。如果只信测试，会以为 fallback 只是"finnhub 挂时 AV 接"——实际是"两层都可能挂"。

## 相关
- 上一篇：[token-extraction-getattr-on-dict](2026-05-04-token-extraction-getattr-on-dict.md) — 同样是"测试 mock 形状错了，prod 行为永远不被覆盖"
- "注释撒谎"模式之后再遇到时，链接到这里
