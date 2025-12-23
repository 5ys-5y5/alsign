-- Seed script: Insert calculation codes for existing transforms
-- Date: 2025-01-XX
-- Description: Populates calculation column with Python code for each transform type

-- avgFromQuarter: 분기 시계열 평균
UPDATE config_lv2_metric_transform
SET calculation = $$
if not quarterly_values:
    return None

window = params.get('window', 4)
recent_quarters = quarterly_values[:window]

if not recent_quarters:
    return None

return sum(recent_quarters) / len(recent_quarters)
$$
WHERE id = 'avgFromQuarter';

-- ttmFromQuarterSumOrScaled: 최근 최대 4분기 합산 TTM. 데이터 부족 시 (sum/n)*4로 환산
UPDATE config_lv2_metric_transform
SET calculation = $$
if not quarterly_values:
    return None

window = params.get('window', 4)
scale_to = params.get('scale_to', 4)
min_points = params.get('min_points', 1)

recent_quarters = quarterly_values[:window]
count = len(recent_quarters)

if count < min_points:
    return None

total = sum(recent_quarters)

if count < scale_to:
    total = (total / count) * scale_to

return total
$$
WHERE id = 'ttmFromQuarterSumOrScaled';

-- lastFromQuarter: 분기 시계열에서 가장 최신 1개 값을 반환
UPDATE config_lv2_metric_transform
SET calculation = $$
if not quarterly_values:
    return None
return quarterly_values[0]
$$
WHERE id = 'lastFromQuarter';

-- qoqFromQuarter: 전분기 대비 증감률(QoQ)
UPDATE config_lv2_metric_transform
SET calculation = $$
if len(quarterly_values) < 2:
    return None

current = quarterly_values[0]
previous = quarterly_values[1]

if previous == 0:
    return None

return (current - previous) / previous
$$
WHERE id = 'qoqFromQuarter';

-- yoyFromQuarter: 전년동기 대비 증감률(YoY)
UPDATE config_lv2_metric_transform
SET calculation = $$
if len(quarterly_values) < 5:
    return None

current = quarterly_values[0]
year_ago = quarterly_values[4]

if year_ago == 0:
    return None

return (current - year_ago) / year_ago
$$
WHERE id = 'yoyFromQuarter';

-- confidenceIntervalByDayOffset: Group base metric by dayOffset and compute mean confidence interval
UPDATE config_lv2_metric_transform
SET calculation = $$
# Group base metric by dayOffset and compute mean confidence interval
# quarterly_values is expected to be a list of dicts with groupBy fields and valueKey
# Returns: scalar confidence interval value

if not quarterly_values:
    return None

group_by = params.get('groupBy', [])
value_key = params.get('valueKey', 'close')
ignore_null = params.get('ignoreNull', True)
z = params.get('z', 1.96)
use = params.get('use', 'z')
level = params.get('level', 0.95)

# Extract values grouped by groupBy fields
grouped_values = {}
for item in quarterly_values:
    if not isinstance(item, dict):
        continue
    
    # Build group key from groupBy fields
    group_key_parts = []
    for field in group_by:
        value = item.get(field)
        if value is None:
            break
        group_key_parts.append(str(value))
    else:
        group_key = tuple(group_key_parts)
        value = item.get(value_key)
        
        if ignore_null and value is None:
            continue
        
        if group_key not in grouped_values:
            grouped_values[group_key] = []
        grouped_values[group_key].append(float(value))

# Calculate mean confidence interval across all groups
if not grouped_values:
    return None

all_means = []
for group_values in grouped_values.values():
    if not group_values:
        continue
    n = len(group_values)
    if n < 2:
        continue
    mean_val = sum(group_values) / n
    all_means.append(mean_val)

if not all_means:
    return None

# Overall mean
overall_mean = sum(all_means) / len(all_means)

# Standard error of the mean (simplified)
if len(all_means) < 2:
    return overall_mean

variance = sum((x - overall_mean) ** 2 for x in all_means) / (len(all_means) - 1)
std_error = (variance / len(all_means)) ** 0.5

# Confidence interval
if use == 'z':
    margin = z * std_error
    return margin
else:
    # t-distribution approximation (simplified)
    margin = z * std_error
    return margin
$$
WHERE id = 'confidenceIntervalByDayOffset';

-- emitReturnSeriesFromEvents: 이벤트 데이터를 기반으로 수익률 시계열 생성
UPDATE config_lv2_metric_transform
SET calculation = $$
# Generate return series from event data
# quarterly_values is expected to be a list of event dicts
# Returns: list of return values per dayOffset

if not quarterly_values:
    return None

base_key = params.get('baseKey', 'value_qualitative.consensusSignal.last.price_when_posted')
close_key = params.get('closeKey', 'price_trend.close')
day_offset_key = params.get('dayOffsetKey', 'dayOffset')
formula = params.get('formula', '(close / base) - 1')
ignore_null = params.get('ignoreNull', True)

return_series = []

for event in quarterly_values:
    if not isinstance(event, dict):
        continue
    
    # Extract base price using dot notation path
    base_price = None
    if base_key:
        keys = base_key.split('.')
        value = event
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                value = None
                break
        base_price = value
    
    if base_price is None or base_price == 0:
        if ignore_null:
            continue
        else:
            return_series.append(None)
            continue
    
    # Extract price_trend (list of dicts with dayOffset and close)
    price_trend = event.get('price_trend', [])
    if isinstance(price_trend, str):
        try:
            price_trend = json.loads(price_trend)
        except:
            price_trend = []
    
    if not isinstance(price_trend, list):
        if ignore_null:
            continue
        else:
            return_series.append(None)
            continue
    
    # Extract close price for each dayOffset
    for trend_item in price_trend:
        if not isinstance(trend_item, dict):
            continue
        
        day_offset = trend_item.get(day_offset_key)
        close_price = trend_item.get(close_key)
        
        if close_price is None or close_price == 0:
            if ignore_null:
                continue
            else:
                return_series.append(None)
                continue
        
        # Calculate return using formula: (close / base) - 1
        ret = (float(close_price) / float(base_price)) - 1
        return_series.append(ret)

return return_series if return_series else None
$$
WHERE id = 'emitReturnSeriesFromEvents';

-- leadPairFromList: PartitionBy + OrderBy 기반으로 리스트를 정렬한 뒤 lead 값을 각 row에 붙임
UPDATE config_lv2_metric_transform
SET calculation = $$
# Add lead (previous row) values to each row based on partitionBy and orderBy
# quarterly_values is expected to be a list of dicts (rows)
# Returns: list of dicts with lead fields added

if not quarterly_values:
    return None

partition_by = params.get('partitionBy', [])
order_by = params.get('orderBy', [])
lead_fields = params.get('leadFields', [])
emit_prev_row = params.get('emitPrevRow', False)

if not partition_by or not order_by or not lead_fields:
    return quarterly_values

# Group rows by partitionBy fields
partitioned = {}
for row in quarterly_values:
    if not isinstance(row, dict):
        continue
    
    # Build partition key
    partition_key_parts = []
    for field in partition_by:
        value = row.get(field)
        if value is None:
            partition_key_parts.append(None)
        else:
            partition_key_parts.append(str(value))
    partition_key = tuple(partition_key_parts)
    
    if partition_key not in partitioned:
        partitioned[partition_key] = []
    partitioned[partition_key].append(row)

# Sort each partition by orderBy and add lead fields
result = []
for partition_key, rows in partitioned.items():
    # Sort rows by orderBy
    def sort_key(row):
        sort_values = []
        for order_spec in order_by:
            if isinstance(order_spec, dict):
                for field, direction in order_spec.items():
                    value = row.get(field)
                    # Handle desc order
                    if direction == 'desc':
                        # Use negative for numeric, reverse for string
                        if isinstance(value, (int, float)):
                            value = -value
                        else:
                            value = str(value)[::-1] if value else ''
                    sort_values.append(value)
        return tuple(sort_values)
    
    sorted_rows = sorted(rows, key=sort_key)
    
    # Add lead fields to each row
    for i, row in enumerate(sorted_rows):
        new_row = dict(row)
        
        # Find previous row (lead)
        if i > 0:
            prev_row = sorted_rows[i - 1]
            for lead_spec in lead_fields:
                field = lead_spec.get('field')
                as_field = lead_spec.get('as')
                if field and as_field:
                    new_row[as_field] = prev_row.get(field)
        else:
            # First row in partition - set lead fields to None
            for lead_spec in lead_fields:
                as_field = lead_spec.get('as')
                if as_field:
                    new_row[as_field] = None
        
        result.append(new_row)

return result if result else None
$$
WHERE id = 'leadPairFromList';

-- proficiencyRateByDayOffset: Group base metric by dayOffset and compute rate >= cutScore
UPDATE config_lv2_metric_transform
SET calculation = $$
# Group base metric by dayOffset and compute rate >= cutScore
# quarterly_values is expected to be a list of dicts with groupBy fields and valueKey
# Returns: scalar rate value

if not quarterly_values:
    return None

group_by = params.get('groupBy', [])
value_key = params.get('valueKey', 'close')
cut_score = params.get('cutScore', 60)
direction = params.get('direction', 'gte')  # 'gte', 'lte', 'eq'
ignore_null = params.get('ignoreNull', True)

# Extract values grouped by groupBy fields
grouped_values = {}
for item in quarterly_values:
    if not isinstance(item, dict):
        continue
    
    # Build group key from groupBy fields
    group_key_parts = []
    for field in group_by:
        value = item.get(field)
        if value is None:
            break
        group_key_parts.append(str(value))
    else:
        group_key = tuple(group_key_parts)
        value = item.get(value_key)
        
        if ignore_null and value is None:
            continue
        
        if group_key not in grouped_values:
            grouped_values[group_key] = []
        grouped_values[group_key].append(float(value))

# Calculate proficiency rate across all groups
if not grouped_values:
    return None

total_count = 0
pass_count = 0

for group_values in grouped_values.values():
    for value in group_values:
        total_count += 1
        if direction == 'gte':
            if value >= cut_score:
                pass_count += 1
        elif direction == 'lte':
            if value <= cut_score:
                pass_count += 1
        elif direction == 'eq':
            if value == cut_score:
                pass_count += 1

if total_count == 0:
    return None

return pass_count / total_count
$$
WHERE id = 'proficiencyRateByDayOffset';

-- statsByDayOffset: Group base metric by analyst_name+analyst_company+dayOffset and compute stats
UPDATE config_lv2_metric_transform
SET calculation = $$
# Group base metric by analyst_name+analyst_company+dayOffset and compute stats
# quarterly_values is expected to be a list of dicts with groupBy fields and valueKey
# Returns: scalar statistic value

if not quarterly_values:
    return None

group_by = params.get('groupBy', [])
value_key = params.get('valueKey', 'close')
stat = params.get('stat', 'mean')  # 'mean', 'median', 'stddev', 'min', 'max', 'count'
ignore_null = params.get('ignoreNull', True)

# Extract values grouped by groupBy fields
grouped_values = {}
for item in quarterly_values:
    if not isinstance(item, dict):
        continue
    
    # Build group key from groupBy fields
    group_key_parts = []
    for field in group_by:
        value = item.get(field)
        if value is None:
            break
        group_key_parts.append(str(value))
    else:
        group_key = tuple(group_key_parts)
        value = item.get(value_key)
        
        if ignore_null and value is None:
            continue
        
        if group_key not in grouped_values:
            grouped_values[group_key] = []
        grouped_values[group_key].append(float(value))

# Collect all values across groups
all_values = []
for group_values in grouped_values.values():
    all_values.extend(group_values)

if not all_values:
    return None

# Calculate requested statistic
if stat == 'mean':
    return sum(all_values) / len(all_values)
elif stat == 'median':
    sorted_vals = sorted(all_values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    else:
        return sorted_vals[n // 2]
elif stat == 'stddev':
    if len(all_values) < 2:
        return 0.0
    mean_val = sum(all_values) / len(all_values)
    variance = sum((x - mean_val) ** 2 for x in all_values) / (len(all_values) - 1)
    return variance ** 0.5
elif stat == 'min':
    return min(all_values)
elif stat == 'max':
    return max(all_values)
elif stat == 'count':
    return len(all_values)
else:
    # Default to mean
    return sum(all_values) / len(all_values)
$$
WHERE id = 'statsByDayOffset';

