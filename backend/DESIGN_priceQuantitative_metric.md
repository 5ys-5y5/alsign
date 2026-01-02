# priceQuantitative Metric Design (I-41)

**Date**: 2026-01-02
**Issue**: I-41
**Replaces**: I-36, I-38, I-40 (deprecated)
**Reference**: `prompt/1_guideline(function).ini`:892-897

---

## 📋 Background

### Original Design Requirement

From `1_guideline(function).ini`:

```ini
position_quantitative: [table.metric] 테이블의 priceQuantitative인 값이
                      [table.metric] 테이블의 price 값보다 작다면 short, 크다면 long
    - 출력 예시: "long" | "short" | "undefined"

disparity_quantitative: {([table.metric] 테이블의 priceQuantitative인 값) /
                        ([table.metric] 테이블의 price 값)} - 1 값 기록
    - 출력 예시: -0.2
```

### Problem

The `priceQuantitative` metric was **never implemented** in the `config_lv2_metric` table. Instead, a temporary workaround was created:

- **I-36**: Added `calcFairValue` parameter to calculate fair value on-demand
- **I-38**: Changed `calcFairValue` default from `false` to `true`
- **I-40**: Documented NULL behavior when peer tickers don't exist

This created a **design discrepancy** between the specification and implementation.

---

## 🎯 Solution: Implement priceQuantitative Metric

### Metric Definition

**Table**: `config_lv2_metric`

| Column | Value |
|--------|-------|
| **id** | `priceQuantitative` |
| **description** | Fair value price based on sector-average valuation multiples. Calculated as: sector_avg_PER × EPS (or sector_avg_PBR × BPS if PER unavailable). Uses fmp-stock-peers API to determine peer group. Returns NULL if no peer tickers available. |
| **source** | `custom` |
| **domain** | `quantitative-valuation` |
| **aggregation_params** | `{"calculation_method": "sector_average_fair_value", "peer_api": "fmp-stock-peers", "valuation_metrics": ["PER", "PBR"], "max_peers": 10, "outlier_removal": "iqr_1.5"}` |

### Calculation Logic

The metric integrates the **calcFairValue** logic developed in I-36:

#### Step 1: Get Peer Tickers
```python
# backend/src/services/valuation_service.py:get_peer_tickers()
peer_tickers = await fmp_client.call_api('fmp-stock-peers', {'ticker': ticker})
```

#### Step 2: Calculate Sector Averages
```python
# backend/src/services/valuation_service.py:calculate_sector_average_metrics()
# For each peer ticker (max 10):
#   1. Fetch API data (income-statement, balance-sheet, etc.)
#   2. Calculate PER, PBR using metric engine
#   3. Collect values
#
# Apply IQR outlier removal (1.5 × IQR)
# Calculate mean of filtered values
sector_averages = {'PER': 25.5, 'PBR': 3.2}
```

#### Step 3: Calculate Fair Value
```python
# backend/src/services/valuation_service.py:calculate_fair_value_from_sector()
# Primary: Use PER
if current_per and sector_avg_per:
    eps = current_price / current_per
    fair_value = sector_avg_per * eps

# Fallback: Use PBR
elif current_pbr and sector_avg_pbr:
    bps = current_price / current_pbr
    fair_value = sector_avg_pbr * bps

# Result
return fair_value  # This is priceQuantitative
```

#### Step 4: Calculate position_quantitative and disparity_quantitative

```python
# backend/src/services/valuation_service.py (existing logic)
if fair_value and current_price:
    position = 'long' if fair_value > current_price else 'short'
    disparity = (fair_value / current_price) - 1
```

---

## 🔧 Implementation Strategy

### 1. Database Update

Execute `backend/scripts/add_priceQuantitative_metric.sql`:

```sql
INSERT INTO config_lv2_metric (id, source, domain, ...)
VALUES ('priceQuantitative', 'custom', 'quantitative-valuation', ...);
```

### 2. Metric Engine Update

**File**: `backend/src/services/metric_engine.py`

Add support for `source='custom'`:

```python
def calculate_metric(self, metric_name: str, api_cache: Dict) -> Any:
    metric = self.metrics_by_name[metric_name]

    if metric['source'] == 'custom':
        # Delegate to custom calculation handlers
        return self._calculate_custom_metric(metric, api_cache)
    elif metric['source'] == 'api_field':
        ...
```

### 3. Valuation Service Integration

**File**: `backend/src/services/valuation_service.py`

The existing functions remain:
- `get_peer_tickers()` - fetch peer tickers from FMP API
- `calculate_sector_average_metrics()` - compute sector averages
- `calculate_fair_value_from_sector()` - compute fair value
- `calculate_fair_value_for_ticker()` - orchestrate the above

**Change**: Instead of being called only when `calc_fair_value=True`, these functions are now called automatically when `priceQuantitative` metric is requested.

### 4. Remove calcFairValue Parameter (Future)

Once priceQuantitative is fully integrated:
- Remove `calc_fair_value` parameter from `BackfillEventsTableRequest`
- Remove conditional logic in `calculate_valuations()`
- The metric engine will automatically calculate `priceQuantitative` when defined in `metrics_by_domain`

---

## 📊 Metric Inclusion in Results

### value_quantitative Structure

```json
{
  "value_quantitative": {
    "valuation": {
      "PER": 28.5,
      "PBR": 7.2,
      "priceQuantitative": 185.0  // <- New metric
    }
  }
}
```

### position_quantitative Calculation

```python
# Original design from 1_guideline(function).ini
price = value_quantitative['valuation']['price']  # Current price
price_quant = value_quantitative['valuation']['priceQuantitative']  # Fair value

if price_quant > price:
    position_quantitative = 'long'
elif price_quant < price:
    position_quantitative = 'short'
else:
    position_quantitative = 'undefined'
```

### disparity_quantitative Calculation

```python
# Original design from 1_guideline(function).ini
disparity_quantitative = (price_quant / price) - 1
# Example: (185.0 / 200.0) - 1 = -0.075
```

---

## ⚠️ Known Limitations

### 1. NULL Values for Small-Cap / Special Sector Stocks

**When**: Peer tickers don't exist in fmp-stock-peers API

**Examples**:
- Small-cap stocks (market cap < $1B)
- Special sectors (Quantum Computing, emerging tech)
- Recently IPO'd companies

**Behavior**:
```json
{
  "value_quantitative": {
    "valuation": {
      "PER": -19.09,
      "PBR": 18.02,
      "priceQuantitative": null  // <- No peer tickers
    }
  },
  "position_quantitative": null,
  "disparity_quantitative": null
}
```

**Log**: `[I-36] No peer tickers found for {ticker}, skipping fair value calculation`

**This is expected behavior** - fair value calculation is meaningless without peer data.

### 2. API Rate Limits

Calculating sector averages requires:
- 1 call to fmp-stock-peers
- Up to 10 × N calls for peer ticker data (N = number of required APIs)

**Mitigation**:
- Limit to max 10 peer tickers
- Cache API responses per event

### 3. Temporal Consistency

**Issue**: fmp-stock-peers returns **current** peer list, not historical

**Implication**: Backfilling historical events uses current peer relationships, which may differ from the actual peer group at that time.

**This is a known limitation of the FMP API** - documented in I-36.

---

## 🔄 Deprecation of I-36, I-38, I-40

### I-36: calcFairValue Parameter Approach

**Status**: 🔄 **DEPRECATED**

**Reason**: Replaced by priceQuantitative metric (I-41). The calculation logic is preserved but is now triggered by the metric definition rather than an explicit parameter.

**Migration**: Remove `calc_fair_value` parameter once I-41 is fully deployed.

### I-38: calcFairValue Default Value Change

**Status**: 🔄 **DEPRECATED**

**Reason**: No longer needed. The priceQuantitative metric is calculated automatically when included in `metrics_by_domain`.

**Migration**: Remove default value logic once I-41 is deployed.

### I-40: NULL Handling for Missing Peer Tickers

**Status**: 🔄 **DEPRECATED** (as standalone issue)

**Reason**: Now documented as a known limitation of priceQuantitative metric (see above).

**Migration**: The NULL behavior remains the same, but is now part of the metric specification rather than a parameter side-effect.

---

## 📁 Files Modified

| File | Change | Reason |
|------|--------|--------|
| `backend/scripts/add_priceQuantitative_metric.sql` | **NEW** | Insert priceQuantitative into config_lv2_metric |
| `backend/DESIGN_priceQuantitative_metric.md` | **NEW** | This design document |
| `backend/src/services/metric_engine.py` | TODO | Add support for source='custom' |
| `backend/src/services/valuation_service.py` | TODO | Integrate with metric engine |
| `history/1_CHECKLIST.md` | TODO | Mark I-36, I-38, I-40 as deprecated |
| `history/2_FLOW.md` | TODO | Document deprecation flow |
| `history/3_DETAIL.md` | TODO | Add I-41 details and deprecation notes |

---

## ✅ Next Steps

1. **Execute SQL script**: `backend/scripts/add_priceQuantitative_metric.sql`
2. **Update metric engine**: Add custom metric handler
3. **Test**: Run POST /backfillEventsTable with priceQuantitative metric
4. **Verify**: Check that position_quantitative and disparity_quantitative are calculated correctly
5. **Remove**: calcFairValue parameter (once verified)

---

*Created: 2026-01-02*
*Issue: I-41*
*Design Decision: Implement original specification (Option A)*
