-- Update config_lv2_metric.consensus to use dynamic calculation
-- Follows the minorityInterest pattern: internal (raw data) → domain (processed data)
-- Step 1: priceTarget (internal) fetches raw API data
-- Step 2: consensus (qualitative-valuation) processes priceTarget

UPDATE config_lv2_metric
SET
    source = 'custom',
    base_metric_id = 'priceTarget',  -- Use priceTarget from internal domain
    api_list_id = NULL,  -- No direct API access, use base_metric_id instead
    response_key = NULL,  -- Custom source doesn't use response_key
    calculation = $CALCULATION$
# Consensus calculation from priceTarget (internal metric)
# Outputs: targetSummary (multi-period stats), consensusSignal (last vs prev)
# Pattern: Similar to minorityInterestLatest using minorityInterest as base

# datetime and timedelta are provided in globals
# Get priceTarget from calculated_values (internal metric)
price_target_data = calculated_values.get('priceTarget', [])

if not price_target_data or not isinstance(price_target_data, list):
    result = {
        '_meta': {
            'source': 'evt_consensus.target_summary',
            'event_date': event_date.isoformat() if hasattr(event_date, 'isoformat') else str(event_date) if event_date else None,
            'dataAvailable': False
        },
        'targetMedian': None,
        'targetSummary': None,
        'consensusSignal': None
    }
else:
    # Convert event_date to date object
    if event_date:
        if isinstance(event_date, str):
            try:
                event_date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00')).date()
            except:
                event_date_obj = datetime.now().date()
        elif hasattr(event_date, 'date'):
            event_date_obj = event_date.date()
        else:
            event_date_obj = event_date
    else:
        event_date_obj = datetime.now().date()

    # Parse all valid records
    # Note: We use ALL records because evt_consensus.event_date is the collection date,
    # not the actual analyst publication date. FMP API doesn't provide historical data.
    all_targets = []
    for record in price_target_data:
        try:
            price_target = record.get('priceTarget') or record.get('adjPriceTarget')
            price_when_posted = record.get('priceWhenPosted')

            # Convert to float to handle Decimal types from DB
            if price_target:
                try:
                    price_target_float = float(price_target)
                except (ValueError, TypeError):
                    continue

                if price_target_float > 0:
                    # Extract publishedDate if available
                    published_date = None
                    published_date_str = record.get('publishedDate')
                    if published_date_str:
                        try:
                            if hasattr(published_date_str, 'date'):
                                published_date = published_date_str.date()
                            else:
                                published_date = datetime.fromisoformat(str(published_date_str).replace('Z', '+00:00')).date()
                        except:
                            published_date = None

                    all_targets.append({
                        'priceTarget': price_target_float,
                        'priceWhenPosted': float(price_when_posted) if price_when_posted else None,
                        'publishedDate': published_date,
                        'analystCompany': record.get('analystCompany', ''),
                    })
        except Exception:
            continue

    if not all_targets:
        result = {
            '_meta': {
                'source': 'evt_consensus.target_summary',
                'event_date': event_date_obj.isoformat(),
                'dataAvailable': False
            },
            'targetMedian': None,
            'targetSummary': None,
            'consensusSignal': None
        }
    else:
        # Sort by published date (newest first)
        all_targets_sorted = sorted(all_targets, key=lambda x: x['publishedDate'], reverse=True)

        # Calculate period cutoff dates
        one_month_ago = event_date_obj - timedelta(days=30)
        one_quarter_ago = event_date_obj - timedelta(days=90)
        one_year_ago = event_date_obj - timedelta(days=365)

        # Filter by periods (using loops instead of list comprehension to avoid exec() scoping issues)
        last_month_targets = []
        last_quarter_targets = []
        last_year_targets = []
        for t in all_targets:
            pub_date = t['publishedDate']
            if pub_date >= one_year_ago:
                last_year_targets.append(t)
            if pub_date >= one_quarter_ago:
                last_quarter_targets.append(t)
            if pub_date >= one_month_ago:
                last_month_targets.append(t)

        # Calculate averages
        def calc_avg(targets):
            if not targets:
                return None
            return sum(t['priceTarget'] for t in targets) / len(targets)

        # Collect unique publishers
        publishers = list(set(t['analystCompany'] for t in all_targets if t['analystCompany']))

        # Calculate median from all targets
        all_price_targets = [t['priceTarget'] for t in all_targets]
        target_median = statistics.median(all_price_targets) if all_price_targets else None

        # Build targetSummary
        target_summary = {
            'publishers': publishers,
            'allTimeCount': len(all_targets),
            'lastYearCount': len(last_year_targets),
            'lastMonthCount': len(last_month_targets),
            'lastQuarterCount': len(last_quarter_targets),
            'allTimeAvgPriceTarget': calc_avg(all_targets),
            'lastYearAvgPriceTarget': calc_avg(last_year_targets),
            'lastMonthAvgPriceTarget': calc_avg(last_month_targets),
            'lastQuarterAvgPriceTarget': calc_avg(last_quarter_targets)
        }

        # Build consensusSignal (compare last vs prev)
        consensus_signal = None
        if len(all_targets_sorted) >= 2:
            last = all_targets_sorted[0]
            prev = all_targets_sorted[1]

            delta = last['priceTarget'] - prev['priceTarget']
            delta_pct = (delta / prev['priceTarget'] * 100) if prev['priceTarget'] != 0 else 0
            direction = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'

            consensus_signal = {
                'last': {
                    'price_target': last['priceTarget'],
                    'price_when_posted': last['priceWhenPosted']
                },
                'prev': {
                    'price_target': prev['priceTarget'],
                    'price_when_posted': prev['priceWhenPosted']
                },
                'delta': delta,
                'deltaPct': delta_pct,
                'direction': direction
            }
        elif len(all_targets_sorted) == 1:
            last = all_targets_sorted[0]
            consensus_signal = {
                'last': {
                    'price_target': last['priceTarget'],
                    'price_when_posted': last['priceWhenPosted']
                },
                'prev': None,
                'delta': None,
                'deltaPct': None,
                'direction': None
            }

        result = {
            '_meta': {
                'source': 'evt_consensus.target_summary',
                'event_date': event_date_obj.isoformat(),
                'dataAvailable': True
            },
            'targetMedian': target_median,
            'targetSummary': target_summary,
            'consensusSignal': consensus_signal
        }
$CALCULATION$,
    description = 'Consensus price target from analysts. Uses priceTarget (internal) as base metric. Returns targetSummary (multi-period statistics) and consensusSignal (last vs prev comparison).'
WHERE id = 'consensus';

-- Verify the update
SELECT id, domain, source, base_metric_id, api_list_id,
       LEFT(calculation, 100) as calculation_preview,
       LEFT(description, 100) as description_preview
FROM config_lv2_metric
WHERE id IN ('priceTarget', 'consensus')
ORDER BY domain, id;
