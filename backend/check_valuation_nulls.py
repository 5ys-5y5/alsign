"""Check NULL values in valuation columns of txn_events table."""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def check_valuation_nulls():
    """Check NULL values in valuation columns."""

    database_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(database_url, statement_cache_size=0)

    try:
        print("=" * 80)
        print("TXN_EVENTS VALUATION COLUMNS NULL ANALYSIS")
        print("=" * 80)
        print()

        # 1. Total count
        total_count = await conn.fetchval("SELECT COUNT(*) FROM txn_events")
        print(f"Total events in txn_events: {total_count:,}")
        print()

        # 2. NULL counts for each valuation column
        null_stats = await conn.fetch("""
            SELECT
                COUNT(*) FILTER (WHERE value_quantitative IS NULL) as null_value_quant,
                COUNT(*) FILTER (WHERE position_quantitative IS NULL) as null_position_quant,
                COUNT(*) FILTER (WHERE disparity_quantitative IS NULL) as null_disparity_quant,
                COUNT(*) FILTER (WHERE value_qualitative IS NULL) as null_value_qual,
                COUNT(*) FILTER (WHERE position_qualitative IS NULL) as null_position_qual,
                COUNT(*) FILTER (WHERE disparity_qualitative IS NULL) as null_disparity_qual,
                COUNT(*) FILTER (
                    WHERE value_quantitative IS NOT NULL
                    AND position_quantitative IS NOT NULL
                    AND disparity_quantitative IS NOT NULL
                    AND value_qualitative IS NOT NULL
                    AND position_qualitative IS NOT NULL
                    AND disparity_qualitative IS NOT NULL
                ) as all_populated
            FROM txn_events
        """)

        row = null_stats[0]
        print("NULL counts by column:")
        print(f"  value_quantitative:     {row['null_value_quant']:,} ({row['null_value_quant']/total_count*100:.2f}%)")
        print(f"  position_quantitative:  {row['null_position_quant']:,} ({row['null_position_quant']/total_count*100:.2f}%)")
        print(f"  disparity_quantitative: {row['null_disparity_quant']:,} ({row['null_disparity_quant']/total_count*100:.2f}%)")
        print(f"  value_qualitative:      {row['null_value_qual']:,} ({row['null_value_qual']/total_count*100:.2f}%)")
        print(f"  position_qualitative:   {row['null_position_qual']:,} ({row['null_position_qual']/total_count*100:.2f}%)")
        print(f"  disparity_qualitative:  {row['null_disparity_qual']:,} ({row['null_disparity_qual']/total_count*100:.2f}%)")
        print()
        print(f"Events with ALL valuation columns populated: {row['all_populated']:,} ({row['all_populated']/total_count*100:.2f}%)")
        print()

        # 3. Check RGTI specifically
        print("=" * 80)
        print("RGTI TICKER ANALYSIS")
        print("=" * 80)
        print()

        rgti_count = await conn.fetchval("SELECT COUNT(*) FROM txn_events WHERE ticker = 'RGTI'")
        print(f"Total RGTI events: {rgti_count}")

        if rgti_count > 0:
            rgti_samples = await conn.fetch("""
                SELECT
                    ticker,
                    event_date,
                    source,
                    value_quantitative,
                    position_quantitative,
                    disparity_quantitative,
                    value_qualitative,
                    position_qualitative,
                    disparity_qualitative
                FROM txn_events
                WHERE ticker = 'RGTI'
                ORDER BY event_date DESC
                LIMIT 10
            """)

            print(f"Sample RGTI events (10 most recent):")
            for i, rec in enumerate(rgti_samples, 1):
                print(f"  [{i}] {rec['ticker']} | {rec['event_date']} | {rec['source']}")
                print(f"      value_quant={rec['value_quantitative']}, pos_quant={rec['position_quantitative']}, disp_quant={rec['disparity_quantitative']}")
                print(f"      value_qual={rec['value_qualitative']}, pos_qual={rec['position_qualitative']}, disp_qual={rec['disparity_qualitative']}")
            print()

            # Check if RGTI is in config_lv3_targets
            rgti_in_targets = await conn.fetchval("""
                SELECT COUNT(*) FROM config_lv3_targets WHERE ticker = 'RGTI'
            """)
            print(f"RGTI in config_lv3_targets: {'YES' if rgti_in_targets > 0 else 'NO'}")

            if rgti_in_targets > 0:
                rgti_target_info = await conn.fetchrow("""
                    SELECT * FROM config_lv3_targets WHERE ticker = 'RGTI'
                """)
                print(f"RGTI target info:")
                for k, v in dict(rgti_target_info).items():
                    print(f"  {k}: {v}")
            print()

        # 4. NULL patterns by source
        print("=" * 80)
        print("NULL PATTERNS BY SOURCE")
        print("=" * 80)
        print()

        source_stats = await conn.fetch("""
            SELECT
                source,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE value_quantitative IS NULL) as null_value_quant,
                COUNT(*) FILTER (WHERE position_quantitative IS NULL) as null_position_quant,
                COUNT(*) FILTER (WHERE disparity_quantitative IS NULL) as null_disparity_quant,
                COUNT(*) FILTER (
                    WHERE value_quantitative IS NOT NULL
                    AND position_quantitative IS NOT NULL
                    AND disparity_quantitative IS NOT NULL
                ) as quant_complete
            FROM txn_events
            GROUP BY source
            ORDER BY source
        """)

        print("By source:")
        for row in source_stats:
            print(f"  {row['source']}:")
            print(f"    Total: {row['total']:,}")
            print(f"    value_quant NULL: {row['null_value_quant']:,} ({row['null_value_quant']/row['total']*100:.2f}%)")
            print(f"    position_quant NULL: {row['null_position_quant']:,} ({row['null_position_quant']/row['total']*100:.2f}%)")
            print(f"    disparity_quant NULL: {row['null_disparity_quant']:,} ({row['null_disparity_quant']/row['total']*100:.2f}%)")
            print(f"    Quantitative complete: {row['quant_complete']:,} ({row['quant_complete']/row['total']*100:.2f}%)")
        print()

        # 5. Sample events with NULL valuation columns
        print("=" * 80)
        print("SAMPLE EVENTS WITH NULL VALUATION COLUMNS")
        print("=" * 80)
        print()

        null_samples = await conn.fetch("""
            SELECT
                ticker,
                event_date,
                source,
                source_id,
                value_quantitative,
                position_quantitative,
                disparity_quantitative
            FROM txn_events
            WHERE value_quantitative IS NULL
               OR position_quantitative IS NULL
               OR disparity_quantitative IS NULL
            ORDER BY event_date DESC
            LIMIT 10
        """)

        print("10 most recent events with NULL valuation columns:")
        for i, rec in enumerate(null_samples, 1):
            print(f"  [{i}] {rec['ticker']} | {rec['event_date']} | {rec['source']}")
            print(f"      value_quant={rec['value_quantitative']}, pos_quant={rec['position_quantitative']}, disp_quant={rec['disparity_quantitative']}")
        print()

        # 6. Check if there are events where backfill should have succeeded but didn't
        print("=" * 80)
        print("INVESTIGATING WHY BACKFILL MIGHT HAVE FAILED")
        print("=" * 80)
        print()

        # Get a NULL event and check if it has the necessary data in source tables
        if null_samples:
            sample = null_samples[0]
            print(f"Investigating: {sample['ticker']} | {sample['event_date']} | source={sample['source']}")
            print()

            if sample['source'] == 'consensus':
                # Check evt_consensus
                source_data = await conn.fetchrow("""
                    SELECT * FROM evt_consensus WHERE id = $1
                """, sample['source_id'])

                if source_data:
                    print("Source data from evt_consensus:")
                    for k, v in dict(source_data).items():
                        print(f"  {k}: {v}")
                else:
                    print("WARNING: Source record not found in evt_consensus!")

            elif sample['source'] == 'earning':
                # Check evt_earning
                source_data = await conn.fetchrow("""
                    SELECT * FROM evt_earning WHERE id = $1
                """, sample['source_id'])

                if source_data:
                    print("Source data from evt_earning:")
                    for k, v in dict(source_data).items():
                        print(f"  {k}: {v}")
                else:
                    print("WARNING: Source record not found in evt_earning!")

        print()
        print("=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_valuation_nulls())
