# API Contracts: History Page

**Date**: 2026-01-16
**Feature**: 001-history-performance-page

## Existing Endpoints (No Changes Required)

### GET /history/trades

Fetches raw trades without precomputed metrics.

**Request**:
```
GET /history/trades?page=1&pageSize=1000&sortBy=trade_date&sortOrder=desc
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | integer | 1 | Page number (1-indexed) |
| pageSize | integer | 1000 | Rows per page (max 2000) |
| sortBy | string | - | Column to sort by |
| sortOrder | enum | - | "asc" or "desc" |
| ticker | string | - | Filter by ticker (ILIKE) |
| model | string | - | Filter by model (ILIKE) |
| source | string | - | Filter by source (ILIKE) |
| position | string | - | Filter by position (ILIKE) |
| tradeDateFrom | date | - | Filter trade_date >= |
| tradeDateTo | date | - | Filter trade_date <= |

**Response**:
```json
{
  "data": [
    {
      "ticker": "AAPL",
      "trade_date": "2024-01-15",
      "model": "momentum",
      "source": "manual",
      "position": "long",
      "entry_price": 185.50,
      "exit_price": null,
      "quantity": 100,
      "notes": "Initial entry"
    }
  ],
  "total": 523,
  "page": 1,
  "pageSize": 1000
}
```

**Status Codes**:
- 200: Success
- 400: Invalid parameters
- 401: Unauthorized
- 500: Server error

---

### POST /history/historical-prices

Fetches historical_price JSONB for a list of tickers.

**Request**:
```json
POST /history/historical-prices
Content-Type: application/json

{
  "tickers": ["AAPL", "GOOGL", "MSFT"]
}
```

**Response**:
```json
{
  "data": {
    "AAPL": [
      { "date": "2024-01-15", "open": 185.0, "high": 186.5, "low": 184.2, "close": 185.5 },
      { "date": "2024-01-16", "open": 185.5, "high": 187.0, "low": 185.0, "close": 186.8 }
    ],
    "GOOGL": [
      { "date": "2024-01-15", "open": 142.0, "high": 143.5, "low": 141.5, "close": 143.0 }
    ]
  },
  "missing": ["MSFT"]
}
```

**Notes**:
- historical_price may be array or `{ historical: [...] }` - normalize on client
- missing array lists tickers with no historical_price data

**Status Codes**:
- 200: Success
- 401: Unauthorized
- 500: Server error

---

## Client-Side Contracts

### localStorage: ui.history_settings

```typescript
interface HistorySettings {
  baseOffset: number;      // 0-14, default: 0
  baseField: 'open' | 'high' | 'low' | 'close';  // default: 'close'
  minThreshold: number | null;  // percentage (e.g., -10), default: null
  maxThreshold: number | null;  // percentage (e.g., 20), default: null
}
```

### localStorage: ui.history_state

```typescript
interface HistoryState {
  selectedColumns: string[];
  filters: Record<string, any>;
  sort: { key: string | null; direction: 'asc' | 'desc' | null };
  dayOffsetMode: 'performance' | 'price_trend';
}
```

### localStorage: ui.history_cache_token

```typescript
type HistoryCacheToken = number;  // timestamp (Date.now())
```

---

## Event Contracts

### Cache Refresh Event

**Trigger**: Settings change, manual Update button

**Flow**:
1. `requestHistoryCacheRefresh()` generates new token
2. Token stored in localStorage
3. All subscribers notified via callback
4. HistoryPage re-fetches and recalculates

**Subscription API**:
```javascript
// Subscribe
const unsubscribe = subscribeHistoryCacheRefresh((newToken) => {
  // Handle refresh
});

// Trigger
requestHistoryCacheRefresh();
```
