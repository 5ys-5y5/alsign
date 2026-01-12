-- Update priceQuantitative definition to include PSR fallback and method tracking
UPDATE config_lv2_metric
SET description = $$
Fair value price based on sector-average valuation multiples. Calculated as:
sector_avg_PER * EPS (or sector_avg_PBR * BPS if PER unavailable, or
sector_avg_PSR * SPS if PER/PBR unavailable). Uses fmp-stock-peers API to
determine peer group. Returns NULL if no peer tickers available.

Fair value calculation from sector averages (Python implementation)

  Formula:
    Priority 1: PER method
      fair_value = sector_avg_per * eps
      where eps = current_price / current_per

    Priority 2: PBR method (fallback)
      fair_value = sector_avg_pbr * bps
      where bps = current_price / current_pbr

    Priority 3: PSR method (fallback)
      fair_value = sector_avg_psr * sps
      where sps = current_price / current_psr

  Sector average calculation:
    - IQR outlier removal (Q1 - 1.5*IQR ~ Q3 + 1.5*IQR)
    - Uses config_lv2_metric_transform.avgWithIQROutlierRemoval
    - Filters extreme values to avoid skewing by outliers

  Implementation location:
    - File: backend/src/services/valuation_service.py
    - Function: calculate_fair_value_from_sector_with_method()

  Method tracking:
    - peer_quantitative.fairValueMethod stores PER/PBR/PSR

  Cannot migrate to config because:
    - Requires cross-ticker async DB queries
    - Needs peer ticker collection and aggregation
    - Peer data must be materialized before calculation
    - Would require complex dependency management

  Dependencies:
    - fmp-stock-peers API (peer ticker list)
    - txn_events table (historical metrics for peers)
    - avgWithIQROutlierRemoval transform (for sector averages)

  Related metrics (NOT in config):
    - position_quant: long/short/neutral (simple comparison logic)
    - disparity_quant: (fair_value / current_price) - 1
    - Both kept in Python for simplicity
$$,
aggregation_params = jsonb_build_object(
    'peer_api', 'fmp-stock-peers',
    'max_peers', 10,
    'outlier_removal', 'iqr_1.5',
    'valuation_metrics', jsonb_build_array('PER', 'PBR', 'PSR'),
    'calculation_method', 'sector_average_fair_value',
    'method_record_field', 'peer_quantitative.fairValueMethod'
),
calculation = $$
# Calculated in valuation_service.py (custom metric with PER/PBR/PSR fallback)
result = None
$$
WHERE id = 'priceQuantitative';
