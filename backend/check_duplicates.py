"""Analyze duplicate events in txn_events table."""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def analyze_duplicates():
    """Analyze and display duplicate events."""

    database_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(database_url, statement_cache_size=0)

    try:
        print("=" * 80)
        print("DUPLICATE EVENTS ANALYSIS")
        print("=" * 80)
        print()

        # Get all duplicate groups with full details
        duplicates = await conn.fetch("""
            WITH dup_groups AS (
                SELECT ticker, event_date, source
                FROM txn_events
                GROUP BY ticker, event_date, source
                HAVING COUNT(*) > 1
            )
            SELECT
                e.ticker,
                e.event_date,
                e.source,
                e.source_id,
                e.sector,
                e.industry,
                e.created_at
            FROM txn_events e
            INNER JOIN dup_groups dg
                ON e.ticker = dg.ticker
                AND e.event_date = dg.event_date
                AND e.source = dg.source
            ORDER BY e.ticker, e.event_date, e.source, e.source_id
        """)

        if not duplicates:
            print("No duplicates found!")
            return

        print(f"Found {len(duplicates)} duplicate records in total")
        print()

        # Group duplicates by (ticker, event_date, source)
        dup_dict = {}
        for row in duplicates:
            key = (row['ticker'], row['event_date'], row['source'])
            if key not in dup_dict:
                dup_dict[key] = []
            dup_dict[key].append(row)

        print(f"Found {len(dup_dict)} duplicate groups")
        print()

        # Display first 10 groups in detail
        for i, (key, records) in enumerate(list(dup_dict.items())[:10], 1):
            ticker, event_date, source = key
            print(f"[{i}] {ticker} | {event_date} | {source} ({len(records)} records)")

            for j, rec in enumerate(records, 1):
                print(f"    Record {j}:")
                print(f"      source_id  : {rec['source_id']}")
                print(f"      sector     : {rec['sector']}")
                print(f"      industry   : {rec['industry']}")
                print(f"      created_at : {rec['created_at']}")
            print()

        # Check if all duplicates have same sector/industry
        mismatched_enrichment = 0
        for key, records in dup_dict.items():
            sectors = {r['sector'] for r in records}
            industries = {r['industry'] for r in records}
            if len(sectors) > 1 or len(industries) > 1:
                mismatched_enrichment += 1

        print(f"Duplicate groups with mismatched sector/industry: {mismatched_enrichment}")
        print()

        # Check the source tables to understand why duplicates exist
        print("Checking source evt_consensus table for duplicate source_ids...")

        # Get source_ids from duplicates where source='consensus'
        consensus_dups = [r for r in duplicates if r['source'] == 'consensus']
        if consensus_dups:
            source_ids = [r['source_id'] for r in consensus_dups]

            # Check if these source_ids are unique in evt_consensus
            consensus_check = await conn.fetch("""
                SELECT id, ticker, event_date, COUNT(*) OVER (PARTITION BY id) as id_count
                FROM evt_consensus
                WHERE id = ANY($1)
                ORDER BY ticker, event_date
                LIMIT 20
            """, source_ids[:20])

            print(f"Sample from evt_consensus (first 20 source_ids):")
            for rec in consensus_check:
                print(f"  id={rec['id']} | ticker={rec['ticker']} | event_date={rec['event_date']} | id_count={rec['id_count']}")
            print()

        # Check evt_earning similarly
        print("Checking source evt_earning table for duplicate source_ids...")

        earning_dups = [r for r in duplicates if r['source'] == 'earning']
        if earning_dups:
            source_ids = [r['source_id'] for r in earning_dups]

            earning_check = await conn.fetch("""
                SELECT id, ticker, event_date, COUNT(*) OVER (PARTITION BY id) as id_count
                FROM evt_earning
                WHERE id = ANY($1)
                ORDER BY ticker, event_date
                LIMIT 20
            """, source_ids[:20])

            print(f"Sample from evt_earning (first 20 source_ids):")
            for rec in earning_check:
                print(f"  id={rec['id']} | ticker={rec['ticker']} | event_date={rec['event_date']} | id_count={rec['id_count']}")
            print()

        print("=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(analyze_duplicates())
