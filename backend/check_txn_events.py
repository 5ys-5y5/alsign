"""Check txn_events table data integrity and contents."""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

async def check_txn_events():
    """Check txn_events table contents and data quality."""

    database_url = os.getenv('DATABASE_URL')

    # Connect to database (disable statement cache for pgbouncer compatibility)
    conn = await asyncpg.connect(database_url, statement_cache_size=0)

    try:
        print("=" * 80)
        print("TXN_EVENTS TABLE INSPECTION")
        print("=" * 80)
        print()

        # 1. Count total rows
        total_count = await conn.fetchval("SELECT COUNT(*) FROM txn_events")
        print(f"1. Total rows in txn_events: {total_count:,}")
        print()

        # 2. Count by source
        source_counts = await conn.fetch("""
            SELECT source, COUNT(*) as count
            FROM txn_events
            GROUP BY source
            ORDER BY count DESC
        """)

        print("2. Rows by source:")
        for row in source_counts:
            print(f"   {row['source']}: {row['count']:,}")
        print()

        # 3. Check NULL values in key columns
        null_checks = await conn.fetch("""
            SELECT
                COUNT(*) FILTER (WHERE ticker IS NULL) as null_ticker,
                COUNT(*) FILTER (WHERE event_date IS NULL) as null_event_date,
                COUNT(*) FILTER (WHERE source IS NULL) as null_source,
                COUNT(*) FILTER (WHERE source_id IS NULL) as null_source_id,
                COUNT(*) FILTER (WHERE sector IS NULL) as null_sector,
                COUNT(*) FILTER (WHERE industry IS NULL) as null_industry
            FROM txn_events
        """)

        print("3. NULL value checks:")
        null_row = null_checks[0]
        print(f"   ticker IS NULL: {null_row['null_ticker']:,}")
        print(f"   event_date IS NULL: {null_row['null_event_date']:,}")
        print(f"   source IS NULL: {null_row['null_source']:,}")
        print(f"   source_id IS NULL: {null_row['null_source_id']:,}")
        print(f"   sector IS NULL: {null_row['null_sector']:,}")
        print(f"   industry IS NULL: {null_row['null_industry']:,}")
        print()

        # 4. Check enrichment status
        enrichment_stats = await conn.fetch("""
            SELECT
                COUNT(*) FILTER (WHERE sector IS NOT NULL AND industry IS NOT NULL) as fully_enriched,
                COUNT(*) FILTER (WHERE sector IS NULL OR industry IS NULL) as not_enriched,
                COUNT(*) FILTER (WHERE sector IS NULL AND industry IS NULL) as both_null
            FROM txn_events
        """)

        print("4. Enrichment status:")
        enrich_row = enrichment_stats[0]
        print(f"   Fully enriched (sector + industry): {enrich_row['fully_enriched']:,}")
        print(f"   Partially or not enriched: {enrich_row['not_enriched']:,}")
        print(f"   Both sector and industry NULL: {enrich_row['both_null']:,}")
        if total_count > 0:
            enrichment_pct = (enrich_row['fully_enriched'] / total_count) * 100
            print(f"   Enrichment rate: {enrichment_pct:.2f}%")
        print()

        # 5. Date range
        date_range = await conn.fetch("""
            SELECT
                MIN(event_date) as earliest_event,
                MAX(event_date) as latest_event
            FROM txn_events
        """)

        print("5. Event date range:")
        if date_range and date_range[0]['earliest_event']:
            print(f"   Earliest event: {date_range[0]['earliest_event']}")
            print(f"   Latest event: {date_range[0]['latest_event']}")
        else:
            print("   No date data available")
        print()

        # 6. Check for duplicate events (shouldn't exist due to unique constraint)
        duplicates = await conn.fetch("""
            SELECT ticker, event_date, source, COUNT(*) as dup_count
            FROM txn_events
            GROUP BY ticker, event_date, source
            HAVING COUNT(*) > 1
            LIMIT 10
        """)

        print("6. Duplicate check (by ticker, event_date, source):")
        if duplicates:
            print(f"   WARNING: Found {len(duplicates)} duplicate groups!")
            for dup in duplicates[:5]:
                print(f"   - {dup['ticker']}, {dup['event_date']}, {dup['source']}: {dup['dup_count']} times")
        else:
            print("   [OK] No duplicates found")
        print()

        # 7. Top tickers by event count
        top_tickers = await conn.fetch("""
            SELECT ticker, COUNT(*) as event_count
            FROM txn_events
            GROUP BY ticker
            ORDER BY event_count DESC
            LIMIT 10
        """)

        print("7. Top 10 tickers by event count:")
        for row in top_tickers:
            print(f"   {row['ticker']}: {row['event_count']:,} events")
        print()

        # 8. Sample records
        samples = await conn.fetch("""
            SELECT ticker, event_date, source, source_id, sector, industry
            FROM txn_events
            ORDER BY event_date DESC
            LIMIT 5
        """)

        print("8. Sample records (5 most recent by event_date):")
        for i, row in enumerate(samples, 1):
            print(f"   [{i}] {row['ticker']} | {row['event_date']} | source={row['source']}")
            print(f"       sector={row['sector']} | industry={row['industry']}")
            print(f"       source_id={row['source_id']}")
        print()

        # 9. Check for orphaned events (ticker not in config_lv3_targets)
        orphaned = await conn.fetchval("""
            SELECT COUNT(*)
            FROM txn_events e
            WHERE NOT EXISTS (
                SELECT 1 FROM config_lv3_targets t WHERE t.ticker = e.ticker
            )
        """)

        print("9. Orphaned events (ticker not in config_lv3_targets):")
        print(f"   {orphaned:,} events")
        if total_count > 0:
            orphan_pct = (orphaned / total_count) * 100
            print(f"   Orphan rate: {orphan_pct:.2f}%")
        print()

        # 10. Check source_id validity (should all be valid UUIDs)
        invalid_uuids = await conn.fetchval("""
            SELECT COUNT(*)
            FROM txn_events
            WHERE source_id IS NULL
               OR source_id::text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        """)

        print("10. Source ID validation:")
        if invalid_uuids > 0:
            print(f"   WARNING: {invalid_uuids:,} invalid or NULL source_ids")
        else:
            print("   [OK] All source_ids are valid UUIDs")
        print()

        print("=" * 80)
        print("INSPECTION COMPLETE")
        print("=" * 80)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_txn_events())
