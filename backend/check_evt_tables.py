"""Check evt_* source tables for duplicates."""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def check_evt_tables():
    """Check evt_consensus and evt_earning for duplicate events."""

    database_url = os.getenv('DATABASE_URL')
    conn = await asyncpg.connect(database_url, statement_cache_size=0)

    try:
        print("=" * 80)
        print("EVT_* SOURCE TABLES ANALYSIS")
        print("=" * 80)
        print()

        # Check evt_consensus
        print("=" * 80)
        print("1. EVT_CONSENSUS TABLE")
        print("=" * 80)
        print()

        consensus_total = await conn.fetchval("SELECT COUNT(*) FROM evt_consensus")
        print(f"Total rows: {consensus_total:,}")
        print()

        # Check for duplicate (ticker, event_date) combinations
        consensus_dups = await conn.fetch("""
            SELECT ticker, event_date, COUNT(*) as dup_count, ARRAY_AGG(id ORDER BY id) as ids
            FROM evt_consensus
            GROUP BY ticker, event_date
            HAVING COUNT(*) > 1
            ORDER BY dup_count DESC, ticker, event_date
            LIMIT 10
        """)

        print(f"Duplicate (ticker, event_date) groups: {len(consensus_dups)}")
        if consensus_dups:
            print()
            print("Top 10 duplicate groups:")
            for i, row in enumerate(consensus_dups, 1):
                print(f"  [{i}] {row['ticker']} | {row['event_date']} | {row['dup_count']} duplicates")
                print(f"      IDs: {row['ids'][:3]}...")  # Show first 3 IDs

        # Total duplicate count
        total_consensus_dups = await conn.fetchval("""
            SELECT COUNT(*) - COUNT(DISTINCT (ticker, event_date))
            FROM evt_consensus
        """)
        print()
        print(f"Total duplicate records in evt_consensus: {total_consensus_dups:,}")
        if consensus_total > 0:
            dup_pct = (total_consensus_dups / consensus_total) * 100
            print(f"Duplicate rate: {dup_pct:.2f}%")
        print()

        # Get full details of one duplicate group
        if consensus_dups:
            sample = consensus_dups[0]
            sample_records = await conn.fetch("""
                SELECT *
                FROM evt_consensus
                WHERE ticker = $1 AND event_date = $2
                ORDER BY id
            """, sample['ticker'], sample['event_date'])

            print(f"Sample duplicate group details ({sample['ticker']}, {sample['event_date']}):")
            for i, rec in enumerate(sample_records, 1):
                print(f"  Record {i}:")
                print(f"    id: {rec['id']}")
                print(f"    ticker: {rec['ticker']}")
                print(f"    event_date: {rec['event_date']}")
                # Print all other columns
                other_cols = {k: v for k, v in dict(rec).items() if k not in ['id', 'ticker', 'event_date']}
                for k, v in other_cols.items():
                    print(f"    {k}: {v}")
            print()

        # Check evt_earning
        print("=" * 80)
        print("2. EVT_EARNING TABLE")
        print("=" * 80)
        print()

        earning_total = await conn.fetchval("SELECT COUNT(*) FROM evt_earning")
        print(f"Total rows: {earning_total:,}")
        print()

        # Check for duplicate (ticker, event_date) combinations
        earning_dups = await conn.fetch("""
            SELECT ticker, event_date, COUNT(*) as dup_count, ARRAY_AGG(id ORDER BY id) as ids
            FROM evt_earning
            GROUP BY ticker, event_date
            HAVING COUNT(*) > 1
            ORDER BY dup_count DESC, ticker, event_date
            LIMIT 10
        """)

        print(f"Duplicate (ticker, event_date) groups: {len(earning_dups)}")
        if earning_dups:
            print()
            print("Top 10 duplicate groups:")
            for i, row in enumerate(earning_dups, 1):
                print(f"  [{i}] {row['ticker']} | {row['event_date']} | {row['dup_count']} duplicates")
                print(f"      IDs: {row['ids'][:3]}...")  # Show first 3 IDs

        # Total duplicate count
        total_earning_dups = await conn.fetchval("""
            SELECT COUNT(*) - COUNT(DISTINCT (ticker, event_date))
            FROM evt_earning
        """)
        print()
        print(f"Total duplicate records in evt_earning: {total_earning_dups:,}")
        if earning_total > 0:
            dup_pct = (total_earning_dups / earning_total) * 100
            print(f"Duplicate rate: {dup_pct:.2f}%")
        print()

        # Get full details of one duplicate group
        if earning_dups:
            sample = earning_dups[0]
            sample_records = await conn.fetch("""
                SELECT *
                FROM evt_earning
                WHERE ticker = $1 AND event_date = $2
                ORDER BY id
            """, sample['ticker'], sample['event_date'])

            print(f"Sample duplicate group details ({sample['ticker']}, {sample['event_date']}):")
            for i, rec in enumerate(sample_records, 1):
                print(f"  Record {i}:")
                print(f"    id: {rec['id']}")
                print(f"    ticker: {rec['ticker']}")
                print(f"    event_date: {rec['event_date']}")
                # Print all other columns
                other_cols = {k: v for k, v in dict(rec).items() if k not in ['id', 'ticker', 'event_date']}
                for k, v in other_cols.items():
                    print(f"    {k}: {v}")
            print()

        print("=" * 80)
        print("ANALYSIS COMPLETE")
        print("=" * 80)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_evt_tables())
