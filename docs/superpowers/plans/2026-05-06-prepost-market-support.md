# Pre/Post-Market (Extended-Hours) Quote Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface pre-market and post-market prices end-to-end — fetch with `prepost=True`, label each quote with its US/Eastern session, persist `last_session` per holding, show a UI chip, and warn the Phase 2 LLM when the latest price is an extended-hours print.

**Architecture:** Add a single `session: Literal["pre","regular","post","closed"]` field to `QuoteData` derived from the latest bar's timestamp via the existing `get_market_session()` helper. yfinance is the only provider that can produce a non-`regular` label (pass `prepost=True` to `ticker.history()` and `fast_info`-fallback re-uses the most-recent prepost bar's timestamp). Finnhub / Alpha Vantage paths default `session="regular"` (documented limitation, fallback only). The label flows through `_enrich_with_quote()` → `holding_repo.update_price()` → Mongo `last_session` → `HoldingResponse.last_session` → frontend chip. Phase 2 prompt gets a 3-line stanza injected when current ET session is not `regular`. The "prefer the latest price" rule is automatic: yfinance returns extended-hours bars at the END of `history()` so `iloc[-1]` already wins.

**Tech Stack:** Python 3.12 / FastAPI / motor (async MongoDB) / Pydantic v2 / dataclass / yfinance / pytest / structlog · React 18 / TypeScript / TanStack Query / Vitest / i18next

---

## File Structure

**New files (3):**
- `backend/tests/test_market_session_boundaries.py`
- `backend/tests/test_yfinance_prepost.py`
- `backend/tests/test_phase2_session_stanza.py`

**Modified files (12):**
- `backend/src/services/data_manager/types.py:184-228` — add `session` field to `QuoteData`
- `backend/src/services/finnhub/service.py:63-85` — pass `session="regular"` (fallback can't tell)
- `backend/src/services/market_data/quotes.py:20-53,163-250` — yfinance `_yf_quote_sync` uses `prepost=True`, derives session from last bar's timestamp; AV path returns `session="regular"`
- `backend/src/services/market_data/yfinance_bars.py:52-71` — accept `prepost: bool = False`; pass to `ticker.history()`
- `backend/src/services/market_data/yfinance_indicators.py` — pass `prepost=False` (RTH-only for indicators) explicitly to keep behavior unchanged
- `backend/src/services/data_manager/manager.py:583-663` — `_fetch_quote_yfinance()` uses `ticker.history(period="1d", interval="1m", prepost=True)` for the latest bar timestamp, returns `session=...`; populates `session="regular"` for the AV branch
- `backend/src/models/holding.py:38-40` — add `last_session: str | None`
- `backend/src/database/repositories/holding_repository.py:185-234` — `update_price()` accepts `session: str | None = None`, writes `last_session`
- `backend/src/api/portfolio/holdings.py:81-130` — `_enrich_with_quote()` reads `quote.session`, sets `holding.last_session`, passes session to `update_price`
- `backend/src/api/schemas/portfolio_models.py:58-119` — add `last_session` to `HoldingResponse` and `from_holding`
- `backend/src/agent/portfolio/phase2_decisions.py:60-169` — inject session stanza into `decision_prompt` when `get_market_session(now_utc) != "regular"`
- `frontend/src/types/portfolio.ts:5-19` — add `last_session: string | null` to `Holding`
- `frontend/src/components/portfolio/PortfolioSummaryTable.tsx:24-46,184-204` — extend `pickLatestPriceUpdate` to also return the picked holding's `last_session`; render a session chip after the relative-age dot
- `frontend/public/locales/en/portfolio.json` — add `session` keys
- `frontend/public/locales/zh-CN/portfolio.json` — add `session` keys

**Touched for version bumps & docs (4):**
- `backend/pyproject.toml` — `0.23.0` → `0.24.0`
- `frontend/package.json` — `0.18.1` → `0.19.0`
- `docs/project/versions/backend/CHANGELOG.md`
- `docs/project/versions/frontend/CHANGELOG.md`

**No-touch (verified inheritance):**
- `scripts/refresh_holding_prices.py` — calls into `DataManager.get_quote()` then `holding_repo.update_price()`; once both carry `session`, the cron path automatically persists it.

---

## Task 1: Extend `QuoteData` with `session` field

**Files:**
- Modify: `backend/src/services/data_manager/types.py:184-228`

- [ ] **Step 1: Add the `session` field with a safe default**

```python
from typing import Any, Literal

@dataclass
class QuoteData:
    symbol: str
    price: float
    volume: int
    latest_trading_day: str
    previous_close: float
    change: float
    change_percent: float
    open: float
    high: float
    low: float
    session: Literal["pre", "regular", "post", "closed"] = "regular"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "price": self.price, "volume": self.volume,
            "latest_trading_day": self.latest_trading_day,
            "previous_close": self.previous_close, "change": self.change,
            "change_percent": self.change_percent, "open": self.open,
            "high": self.high, "low": self.low, "session": self.session,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuoteData":
        return cls(
            symbol=data["symbol"], price=float(data["price"]),
            volume=int(data["volume"]),
            latest_trading_day=data["latest_trading_day"],
            previous_close=float(data["previous_close"]),
            change=float(data["change"]),
            change_percent=float(data["change_percent"]),
            open=float(data["open"]), high=float(data["high"]),
            low=float(data["low"]),
            session=data.get("session", "regular"),
        )
```

- [ ] **Step 2: Sanity-check imports**

Run: `docker compose exec backend python -c "from src.services.data_manager.types import QuoteData; q=QuoteData(symbol='X',price=1,volume=0,latest_trading_day='',previous_close=0,change=0,change_percent=0,open=0,high=0,low=0); print(q.session); print(QuoteData.from_dict(q.to_dict()).session)"`

Expected: `regular` then `regular`.

- [ ] **Step 3: Commit**

```bash
git add backend/src/services/data_manager/types.py
git commit -m "feat(quotes): add session field to QuoteData (defaults regular)"
```

---

## Task 2: Wire `prepost=True` and session derivation in providers

**Files:**
- Modify: `backend/src/services/market_data/quotes.py:20-53,163-250`
- Modify: `backend/src/services/market_data/yfinance_bars.py:52-77`
- Modify: `backend/src/services/market_data/yfinance_indicators.py`
- Modify: `backend/src/services/data_manager/manager.py:583-663`
- Modify: `backend/src/services/finnhub/service.py:63-85`

- [ ] **Step 1: Add `prepost` parameter to `yfinance_bars.get_bars`**

```python
def _fetch_sync(symbol, granularity, outputsize, prepost) -> pd.DataFrame:
    spec = _INTERVAL_MAP.get(granularity)
    if spec is None:
        raise ValueError(f"Unsupported granularity: {granularity}")
    interval, period_compact, period_full = spec
    period = period_full if outputsize == "full" else period_compact
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, auto_adjust=False, prepost=prepost)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no bars for {symbol} ({granularity})")
    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    return df[keep].copy()


async def get_bars(symbol, granularity, outputsize="compact", prepost: bool = False):
    """Pass `prepost=True` to include extended-hours bars."""
    return await asyncio.to_thread(_fetch_sync, symbol, granularity, outputsize, prepost)
```

- [ ] **Step 2: Indicators pipeline stays RTH-only**

In `yfinance_indicators.py`, every `get_bars(...)` call gets explicit `prepost=False` for intent-locking. No-op at runtime.

- [ ] **Step 3: yfinance quote — `prepost=True` and derive session from last bar**

In `quotes.py:_yf_quote_sync`:

```python
def _yf_quote_sync(symbol):
    from . import get_market_session
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    hist = ticker.history(period="2d", prepost=True)
    if len(hist) == 0:
        last_close = 0.0
        prev_close = float(info.get("previousClose", 0.0) or 0.0)
        open_p = high_p = low_p = 0.0
        vol = int(info.get("volume", 0) or 0)
        last_ts = pd.Timestamp.now(tz="UTC")
    else:
        last_close = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else float(info.get("previousClose", last_close) or last_close)
        open_p = float(hist["Open"].iloc[-1])
        high_p = float(hist["High"].iloc[-1])
        low_p = float(hist["Low"].iloc[-1])
        vol = int(hist["Volume"].iloc[-1])
        last_ts = hist.index[-1]
        if last_ts.tz is None:
            last_ts = last_ts.tz_localize("UTC")
    price = float(last_close or info.get("currentPrice") or info.get("regularMarketPrice") or 0.0)
    change = price - prev_close
    change_pct = (change / prev_close * 100.0) if prev_close else 0.0
    return {
        "symbol": symbol, "price": price, "volume": vol,
        "latest_trading_day": last_ts.strftime("%Y-%m-%d"),
        "previous_close": prev_close, "change": change,
        "change_percent": f"{change_pct:.4f}",
        "open": open_p, "high": high_p, "low": low_p,
        "session": get_market_session(last_ts),
    }
```

AV branch in same file (around line 227-238): add `"session": "regular"` to the result dict.

- [ ] **Step 4: Finnhub `session="regular"`**

In `finnhub/service.py:fetch_quote`, add `session="regular"` to the `QuoteData(...)` constructor and a docstring noting "Finnhub /quote is RTH-only; can't produce extended-hours labels."

- [ ] **Step 5: DataManager `_fetch_quote_yfinance` derives session from 1m prepost bar**

In `manager.py`:

```python
@staticmethod
async def _fetch_quote_yfinance(symbol):
    import asyncio, pandas as pd, yfinance as yf
    from ..market_data import get_market_session
    def _sync():
        t = yf.Ticker(symbol)
        fi = t.fast_info
        hist = t.history(period="1d", interval="1m", prepost=True)
        if hist is not None and len(hist) > 0:
            last_ts = hist.index[-1]
            if last_ts.tz is None: last_ts = last_ts.tz_localize("UTC")
            price = float(hist["Close"].iloc[-1])
            vol = int(hist["Volume"].iloc[-1] or 0)
            open_p = float(hist["Open"].iloc[0])
            high_p = float(hist["High"].max())
            low_p = float(hist["Low"].min())
        else:
            last_ts = pd.Timestamp.now(tz="UTC")
            price = float(fi.last_price)
            vol = int(getattr(fi, "last_volume", 0) or 0)
            open_p = float(getattr(fi, "open", 0.0) or 0.0)
            high_p = float(getattr(fi, "day_high", 0.0) or 0.0)
            low_p = float(getattr(fi, "day_low", 0.0) or 0.0)
        prev = float(fi.previous_close)
        return QuoteData(
            symbol=symbol.upper(), price=price, volume=vol,
            latest_trading_day=last_ts.strftime("%Y-%m-%d"),
            previous_close=prev, change=price - prev,
            change_percent=((price - prev) / prev * 100) if prev else 0.0,
            open=open_p, high=high_p, low=low_p,
            session=get_market_session(last_ts),
        )
    return await asyncio.to_thread(_sync)
```

- [ ] **Step 6: Smoke**

`docker compose exec backend python -c "from src.services.market_data import get_market_session; from src.services.market_data.quotes import _yf_quote_sync; print('ok')"` → prints `ok`.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(quotes): fetch prepost bars via yfinance and label session"
```

---

## Task 3: Persist `last_session` on holdings

**Files:**
- Modify: `backend/src/models/holding.py`
- Modify: `backend/src/database/repositories/holding_repository.py`
- Modify: `backend/src/api/schemas/portfolio_models.py`

- [ ] **Step 1:** Add `last_session: str | None = Field(None, ...)` to `Holding` after `last_price_update`.

- [ ] **Step 2:** Extend `update_price(self, holding_id, current_price, session: str | None = None)` to write `last_session` only if `session is not None`.

- [ ] **Step 3:** Add `last_session: str | None` to `HoldingResponse` and pipe through `from_holding`.

- [ ] **Step 4:** `python -c "from src.models.holding import Holding; from src.api.schemas.portfolio_models import HoldingResponse; print('last_session' in Holding.model_fields, 'last_session' in HoldingResponse.model_fields)"` → `True True`.

- [ ] **Step 5:** Commit `feat(portfolio): persist last_session per holding`.

---

## Task 4: Wire session through `_enrich_with_quote`

**Files:**
- Modify: `backend/src/api/portfolio/holdings.py:81-130`

- [ ] **Step 1:** Read `session = getattr(quote, "session", None)`, set `holding.last_session = session` if truthy, and pass `session=session` to `holding_repo.update_price(...)` in the persist branch.

- [ ] **Step 2:** Verify cron path. `grep -n "update_price\|get_quote" scripts/refresh_holding_prices.py`. If it calls `update_price` directly, add `session=quote.session` there too.

- [ ] **Step 3:** Smoke:
```bash
H=$(curl -s http://localhost:8001/api/portfolio/holdings | jq -r '.[0].holding_id')
curl -s -X PATCH http://localhost:8001/api/portfolio/holdings/$H -H 'Content-Type: application/json' -d '{}' | jq '{last_price_update, last_session}'
```
Expected: `last_session` is one of `pre|regular|post|closed`.

- [ ] **Step 4:** Commit `feat(portfolio): persist last_session via _enrich_with_quote`.

---

## Task 5: Frontend type, chip, i18n

**Files:**
- Modify: `frontend/src/types/portfolio.ts`
- Modify: `frontend/src/components/portfolio/PortfolioSummaryTable.tsx`
- Modify: `frontend/public/locales/en/portfolio.json`
- Modify: `frontend/public/locales/zh-CN/portfolio.json`

- [ ] **Step 1:** Add `last_session: "pre" | "regular" | "post" | "closed" | null;` to the `Holding` interface.

- [ ] **Step 2:** Add i18n keys:
  - en: `"session": { "pre": "Pre-Market", "post": "After-Hours", "closed": "Closed" }`
  - zh-CN: `"session": { "pre": "盘前", "post": "盘后", "closed": "休市" }`
  - No `"regular"` key — chip hides during RTH.

- [ ] **Step 3:** Change `pickLatestPriceUpdate` to also return the session of the row that won:
```tsx
type LatestUpdate = { date: Date; session: Holding["last_session"] } | null;
function pickLatestPriceUpdate(holdings: Holding[]): LatestUpdate {
  let latestMs = 0; let latestSession: Holding["last_session"] = null;
  for (const h of holdings) {
    if (!h.last_price_update) continue;
    const ms = new Date(h.last_price_update).getTime();
    if (Number.isFinite(ms) && ms > latestMs) {
      latestMs = ms; latestSession = h.last_session ?? null;
    }
  }
  return latestMs > 0 ? { date: new Date(latestMs), session: latestSession } : null;
}
```

- [ ] **Step 4:** Render chip in header:
```tsx
{latestSession && latestSession !== "regular" && (
  <span data-testid="session-chip"
    className="ml-2 inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-800">
    {t(`portfolio:session.${latestSession}`)}
  </span>
)}
```
(Add `t` to the destructure: `const { t, i18n } = useTranslation();`)

- [ ] **Step 5:** `cd frontend && npx tsc --noEmit` → no errors.

- [ ] **Step 6:** Commit `feat(ui): show pre/post-market chip on portfolio header`.

---

## Task 6: Phase 2 prompt — session warning when not regular

**Files:**
- Modify: `backend/src/agent/portfolio/phase2_decisions.py`

- [ ] **Step 1:** Before the `decision_prompt = f"""..."""` block, compute current session and build stanza:

```python
from datetime import UTC, datetime as _dt
import pandas as _pd
from ...services.market_data import get_market_session

_now_utc = _pd.Timestamp(_dt.now(UTC))
current_session = get_market_session(_now_utc)
if current_session == "regular":
    session_stanza = ""
else:
    label = {"pre": "盘前 (pre-market)", "post": "盘后 (after-hours)", "closed": "休市 (closed)"}[current_session]
    session_stanza = (
        "\n## 市场时段提示 (Market Session Notice)\n\n"
        f"当前为 **{label}** 时段。下列研究中的最新价可能来自延长交易时段的成交，"
        "流动性较薄，价差较大，开盘后可能出现明显跳空。请在做决策时考虑：\n"
        "- 是否将下单时间延后至开盘后再确认价格行为；\n"
        "- 若仍要使用延长时段价格作为锚点，是否需要将 entry 略微调整以预留跳空空间；\n"
        "- stop_loss / take_profit 的风险距离是否仍然合理。\n"
        "本提示不强制阻断决策,仅作为风险提醒。\n"
    )
```

- [ ] **Step 2:** Inject `{session_stanza}` into the prompt template right after `{positions_table}` and before `## Symbol Research Results`. When session is regular it collapses to empty string.

- [ ] **Step 3:** `docker compose exec backend python -c "from src.agent.portfolio.phase2_decisions import *; print('ok')"` → prints `ok`.

- [ ] **Step 4:** Commit `feat(phase2): warn LLM when current session is extended-hours`.

---

## Task 7: Tests + smoke

**Files:**
- Create: `backend/tests/test_market_session_boundaries.py`
- Create: `backend/tests/test_yfinance_prepost.py`
- Create: `backend/tests/test_phase2_session_stanza.py`
- Create or modify: `frontend/src/components/portfolio/__tests__/PortfolioSummaryTable.test.tsx`

- [ ] **Step 1:** Boundary tests for `get_market_session` (pre/regular/post/closed transitions on a weekday plus a Sat + Sun). Use `pd.Timestamp(...).tz_localize("America/New_York")`. Assert each.

- [ ] **Step 2:** Network test (`@pytest.mark.network`): `await get_bars("SPY", "5min", prepost=True)` returns ≥ rows of `prepost=False`.

- [ ] **Step 3:** Snapshot test: monkey-patch `get_market_session` to return each non-regular session, call the prompt builder fragment, assert `"市场时段提示"` is in the prompt; for regular assert it's not.

- [ ] **Step 4:** Vitest: render `PortfolioSummaryTable` with three holding fixtures (`last_session: "post"`, `"regular"`, `null`); assert `getByTestId("session-chip")` for `post`, `queryByTestId(...)` returns null for the other two.

- [ ] **Step 5:** Manual smoke:
```bash
H=$(curl -s http://localhost:8001/api/portfolio/holdings | jq -r '.[0].holding_id')
curl -s -X PATCH http://localhost:8001/api/portfolio/holdings/$H -H 'Content-Type: application/json' -d '{}' | jq '.last_session'
```
Open frontend, verify chip outside RTH, hidden in RTH.

- [ ] **Step 6:** Commit `test: cover session label, prepost bars, and chip render`.

---

## Task 8: Version bump + CHANGELOG

- [ ] **Step 1:** `./scripts/bump-version.sh backend minor` → 0.24.0
- [ ] **Step 2:** `./scripts/bump-version.sh frontend minor` → 0.19.0
- [ ] **Step 3:** Backend CHANGELOG `[0.24.0]` block: QuoteData.session field, yfinance prepost, last_session persistence, Phase 2 session stanza. Note Finnhub/AV always `regular`.
- [ ] **Step 4:** Frontend CHANGELOG `[0.19.0]` block: session chip + Holding type field.
- [ ] **Step 5:** Commit `chore(release): backend v0.24.0 / frontend v0.19.0 — pre/post-market`.

---

## Edge cases

- **Stale extended-hours print:** thinly-traded post symbol may show 30+ min old price. Surface anyway per "prefer latest" rule. `formatRelativeAge()` already shows the staleness.
- **Provider asymmetry:** only yfinance produces non-`regular` labels. If Finnhub wins fallback, chip stays hidden. Documented in code + CHANGELOG.
- **Timezone:** `get_market_session()` lives in America/New_York; persisted timestamps stay UTC; conversion at the boundary.
- **Cache compat:** `QuoteData.from_dict(...)` defaults `session="regular"` for old cached entries.
- **Mongo migration:** none. `last_session: Optional[str]`; missing rows = `None`; frontend hides chip on null.
