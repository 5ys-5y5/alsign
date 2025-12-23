#!/usr/bin/env python3
"""
Check current config_lv2_metric table state and compare with proposed changes.

Outputs:
1. Current metrics that might need changes
2. Missing metrics
3. Comparison with proposed changes from BACKFILL_EVENTS_TABLE_ISSUES_AND_SOLUTIONS.md
"""

import asyncio
import asyncpg
import json
from typing import Dict, List, Any

# Database connection
DATABASE_URL = "postgresql://postgres.fgypclaqxonwxlmqdphx:qycKXqvs%40%21Q_Pt3@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

# Metrics to check based on BACKFILL_EVENTS_TABLE_ISSUES_AND_SOLUTIONS.md
METRICS_TO_CHECK = [
    # api_field failures
    'consensus', 'priceAfter', 'priceEodOHLC',

    # Proposed new consensus-related metrics
    'consensusPriceTarget', 'consensusAnalystName', 'consensusAnalystCompany',
    'consensusPriceWhenPosted', 'consensusNewsURL', 'consensusNewsTitle',
    'consensusNewsPublisher', 'consensusPublishedDate',

    # targetMedian and consensusSummary metrics
    'targetMedian',
    'consensusSummaryTargetLow', 'consensusSummaryTargetHigh',
    'consensusSummaryTargetMedian', 'consensusSummaryTargetConsensus',
    'consensusSummary',

    # consensusSignal
    'consensusSignal',

    # aggregation failures
    'apicYoY', 'consensusWithPrev', 'revenueQoQ', 'revenueYoY', 'sharesYoY',

    # expression failures
    'price', 'PER', 'runwayYears', 'grossMarginTTM', 'operatingMarginTTM',
    'rndIntensityTTM', 'cashToRevenueTTM', 'PSR', 'debtToEquityAvg',
    'othernclToEquityAvg', 'ROE', 'netdebtToEquityAvg', 'evEBITDA',

    # Base metrics for TTM
    'revenue', 'netIncome', 'ebitda', 'grossProfit', 'operatingIncome', 'rnd',
    'revenueTTM', 'netIncomeTTM', 'ebitdaTTM', 'grossProfitTTM', 'operatingIncomeTTM', 'rndTTM',

    # Base metrics for avgFromQuarter
    'totalDebt', 'totalEquity', 'otherNCL', 'netDebt',
    'avgTotalDebt', 'avgTotalEquity', 'avgOtherNCL', 'avgNetDebt',

    # Additional base metrics
    'additionalPaidInCapital', 'weightedAverageShsOut', 'cashAndShortTermInvestments',
    'marketCap', 'enterpriseValue', 'priceRegular',
    'cashAndShortTermInvestmentsLast',
]


async def main():
    # Connect to database (disable statement cache for pgbouncer compatibility)
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    try:
        print("=" * 80)
        print("CONFIG_LV2_METRIC TABLE STATE CHECK")
        print("=" * 80)
        print()

        # 1. Check if metrics exist
        print("1. CHECKING METRIC EXISTENCE")
        print("-" * 80)

        existing_metrics = {}
        missing_metrics = []

        for metric_id in METRICS_TO_CHECK:
            row = await conn.fetchrow(
                """
                SELECT id, description, source, api_list_id, base_metric_id,
                       aggregation_kind, aggregation_params, expression, domain, response_key
                FROM config_lv2_metric
                WHERE id = $1
                """,
                metric_id
            )

            if row:
                existing_metrics[metric_id] = dict(row)
            else:
                missing_metrics.append(metric_id)

        print(f"Existing metrics: {len(existing_metrics)}/{len(METRICS_TO_CHECK)}")
        print(f"Missing metrics: {len(missing_metrics)}")
        print()

        if missing_metrics:
            print("Missing metrics:")
            for metric_id in missing_metrics:
                print(f"  - {metric_id}")
            print()

        # 2. Check specific issues mentioned in BACKFILL_EVENTS_TABLE_ISSUES_AND_SOLUTIONS.md
        print("2. CHECKING SPECIFIC ISSUES")
        print("-" * 80)
        print()

        # 2.1 consensus metric - should be changed or split
        if 'consensus' in existing_metrics:
            m = existing_metrics['consensus']
            print("【consensus】")
            print(f"  Current:")
            print(f"    - source: {m['source']}")
            print(f"    - api_list_id: {m['api_list_id']}")
            print(f"    - response_key: {m['response_key']}")
            print(f"    - domain: {m['domain']}")
            print(f"  Issue: Complex dict response_key not supported")
            print(f"  Proposed: Split into consensusPriceTarget, consensusAnalystName, etc.")
            print()

        # 2.2 Check if new consensus metrics exist
        new_consensus_metrics = [
            'consensusPriceTarget', 'consensusAnalystName', 'consensusAnalystCompany',
            'consensusPriceWhenPosted', 'consensusNewsURL', 'consensusNewsTitle',
            'consensusNewsPublisher', 'consensusPublishedDate'
        ]

        existing_new = [m for m in new_consensus_metrics if m in existing_metrics]
        missing_new = [m for m in new_consensus_metrics if m not in existing_metrics]

        print("【New consensus metrics】")
        print(f"  Existing: {len(existing_new)}/{len(new_consensus_metrics)}")
        if missing_new:
            print(f"  Missing: {', '.join(missing_new)}")
        print()

        # 2.3 targetMedian and consensusSummary metrics
        summary_metrics = [
            'targetMedian', 'consensusSummaryTargetLow', 'consensusSummaryTargetHigh',
            'consensusSummaryTargetMedian', 'consensusSummaryTargetConsensus',
            'consensusSummary'
        ]

        existing_summary = [m for m in summary_metrics if m in existing_metrics]
        missing_summary = [m for m in summary_metrics if m not in existing_metrics]

        print("【targetMedian & consensusSummary metrics】")
        print(f"  Existing: {len(existing_summary)}/{len(summary_metrics)}")
        if missing_summary:
            print(f"  Missing: {', '.join(missing_summary)}")
        print()

        # 2.4 consensusSignal metric
        if 'consensusSignal' in existing_metrics:
            m = existing_metrics['consensusSignal']
            print("【consensusSignal】")
            print(f"  Current:")
            print(f"    - source: {m['source']}")
            print(f"    - expression: {m['expression']}")
            print(f"    - domain: {m['domain']}")
            print(f"  Note: Should use evt_consensus table (hardcoded in calculate_qualitative_metrics)")
            print()
        elif 'consensusSignal' in missing_metrics:
            print("【consensusSignal】")
            print(f"  Status: MISSING")
            print(f"  Note: Currently hardcoded in calculate_qualitative_metrics()")
            print()

        # 2.5 priceAfter and priceEodOHLC
        for metric_id in ['priceAfter', 'priceEodOHLC']:
            if metric_id in existing_metrics:
                m = existing_metrics[metric_id]
                print(f"【{metric_id}】")
                print(f"  Current:")
                print(f"    - source: {m['source']}")
                print(f"    - api_list_id: {m['api_list_id']}")
                print(f"    - response_key: {m['response_key']}")
                print(f"  Issue: API data might be missing or response_key incorrect")
                print()

        # 2.6 YoY aggregation metrics
        yoy_metrics = ['apicYoY', 'revenueYoY', 'sharesYoY']
        print("【YoY aggregation metrics】")
        for metric_id in yoy_metrics:
            if metric_id in existing_metrics:
                m = existing_metrics[metric_id]
                print(f"  {metric_id}:")
                print(f"    - base_metric_id: {m['base_metric_id']}")
                print(f"    - aggregation_kind: {m['aggregation_kind']}")
                print(f"    - Issue: Needs 5+ quarters, might fail with insufficient data")
        print()

        # 2.7 QoQ aggregation metrics
        if 'revenueQoQ' in existing_metrics:
            m = existing_metrics['revenueQoQ']
            print("【revenueQoQ】")
            print(f"  Current:")
            print(f"    - base_metric_id: {m['base_metric_id']}")
            print(f"    - aggregation_kind: {m['aggregation_kind']}")
            print(f"  Issue: Base metric might return scalar instead of list")
            print()

        # 2.8 consensusWithPrev
        if 'consensusWithPrev' in existing_metrics:
            m = existing_metrics['consensusWithPrev']
            print("【consensusWithPrev】")
            print(f"  Current:")
            print(f"    - aggregation_kind: {m['aggregation_kind']}")
            print(f"  Issue: leadPairFromList not implemented")
            print(f"  Proposed: Remove or change to use evt_consensus directly")
            print()

        # 2.9 TTM metrics - check base_metric_id
        ttm_metrics = ['revenueTTM', 'netIncomeTTM', 'ebitdaTTM', 'grossProfitTTM', 'operatingIncomeTTM', 'rndTTM']
        print("【TTM aggregation metrics】")
        for metric_id in ttm_metrics:
            if metric_id in existing_metrics:
                m = existing_metrics[metric_id]
                expected_base = metric_id.replace('TTM', '')
                print(f"  {metric_id}:")
                print(f"    - base_metric_id: {m['base_metric_id']} (expected: {expected_base})")
                if m['base_metric_id'] != expected_base:
                    print(f"    - WARNING: base_metric_id mismatch!")
        print()

        # 2.10 avgFromQuarter metrics
        avg_metrics = ['avgTotalDebt', 'avgTotalEquity', 'avgOtherNCL', 'avgNetDebt']
        print("【avgFromQuarter aggregation metrics】")
        for metric_id in avg_metrics:
            if metric_id in existing_metrics:
                m = existing_metrics[metric_id]
                expected_base = metric_id.replace('avg', '', 1)
                expected_base = expected_base[0].lower() + expected_base[1:]  # camelCase
                print(f"  {metric_id}:")
                print(f"    - base_metric_id: {m['base_metric_id']} (expected: {expected_base})")
                if m['aggregation_kind'] != 'avgFromQuarter':
                    print(f"    - WARNING: aggregation_kind = {m['aggregation_kind']} (expected: avgFromQuarter)")
        print()

        # 2.11 price expression
        if 'price' in existing_metrics:
            m = existing_metrics['price']
            print("【price】")
            print(f"  Current:")
            print(f"    - expression: {m['expression']}")
            print(f"  Issue: priceAfter might be None, needs fallback to priceRegular")
            print()

        # 2.12 Expression metrics with TTM dependencies
        expr_with_ttm = ['PER', 'PSR', 'evEBITDA', 'grossMarginTTM', 'operatingMarginTTM', 'rndIntensityTTM', 'cashToRevenueTTM']
        print("【Expression metrics with TTM dependencies】")
        for metric_id in expr_with_ttm:
            if metric_id in existing_metrics:
                m = existing_metrics[metric_id]
                print(f"  {metric_id}:")
                print(f"    - expression: {m['expression']}")
        print(f"  Issue: If TTM metrics return None, these expressions will fail")
        print()

        # 2.13 Expression metrics with avg dependencies
        expr_with_avg = ['debtToEquityAvg', 'othernclToEquityAvg', 'ROE', 'netdebtToEquityAvg']
        print("【Expression metrics with avg dependencies】")
        for metric_id in expr_with_avg:
            if metric_id in existing_metrics:
                m = existing_metrics[metric_id]
                print(f"  {metric_id}:")
                print(f"    - expression: {m['expression']}")
        print(f"  Issue: If avgFromQuarter metrics return None, these expressions will fail")
        print()

        # 3. Check API list IDs
        print("3. CHECKING API LIST IDs")
        print("-" * 80)
        print()

        # Get all unique api_list_ids from metrics
        api_list_ids = set()
        for m in existing_metrics.values():
            if m['api_list_id']:
                api_list_ids.add(m['api_list_id'])

        print(f"Unique api_list_ids used: {len(api_list_ids)}")

        # Check if they exist in config_lv1_api_list
        for api_id in sorted(api_list_ids):
            row = await conn.fetchrow(
                "SELECT id FROM config_lv1_api_list WHERE id = $1",
                api_id
            )
            status = "[OK]" if row else "[MISSING]"
            print(f"  {status} {api_id}")
        print()

        # 4. Check dependencies
        print("4. CHECKING DEPENDENCIES")
        print("-" * 80)
        print()

        # Check base_metric_id references
        print("Checking base_metric_id references:")
        broken_deps = []
        for metric_id, m in existing_metrics.items():
            base_id = m['base_metric_id']
            if base_id:
                base_row = await conn.fetchrow(
                    "SELECT id FROM config_lv2_metric WHERE id = $1",
                    base_id
                )
                if not base_row:
                    broken_deps.append((metric_id, base_id))
                    print(f"  [BROKEN] {metric_id} -> {base_id} (MISSING)")

        if not broken_deps:
            print("  [OK] All base_metric_id references are valid")
        print()

        # 5. Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print()
        print(f"Total metrics checked: {len(METRICS_TO_CHECK)}")
        print(f"Existing: {len(existing_metrics)}")
        print(f"Missing: {len(missing_metrics)}")
        print(f"Broken dependencies: {len(broken_deps)}")
        print()

        if missing_metrics:
            print("Action needed: Add missing metrics")
            print(f"  Count: {len(missing_metrics)}")

        if broken_deps:
            print("Action needed: Fix broken dependencies")
            print(f"  Count: {len(broken_deps)}")

        print()
        print("See BACKFILL_EVENTS_TABLE_ISSUES_AND_SOLUTIONS.md for proposed changes.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
