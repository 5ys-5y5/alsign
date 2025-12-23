#!/usr/bin/env python3
"""
Seed script to populate database with initial test data.

This script creates sample data for testing the AlSign application.
Run this after setting up the database schema.

Usage:
    python backend/scripts/seed_data.py
"""

import asyncio
import asyncpg
import os
from datetime import datetime, timedelta


async def seed_database():
    """Seed the database with initial test data."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return

    print(f"Connecting to database...")

    try:
        conn = await asyncpg.connect(database_url)
        print("✓ Connected to database")

        # Seed config_lv1_api_service
        print("\nSeeding config_lv1_api_service...")
        await conn.execute("""
            INSERT INTO config_lv1_api_service (api_service, apiKey, usagePerMin)
            VALUES
                ('fmp', NULL, 300),
                ('polygon', NULL, 200),
                ('alphavantage', NULL, 100)
            ON CONFLICT (api_service) DO NOTHING
        """)
        print("✓ API services seeded")

        # Seed config_lv3_targets (sample tickers)
        print("\nSeeding config_lv3_targets...")
        sample_tickers = [
            ('AAPL', 'Technology', 'Consumer Electronics'),
            ('MSFT', 'Technology', 'Software'),
            ('GOOGL', 'Technology', 'Internet Services'),
            ('TSLA', 'Automotive', 'Electric Vehicles'),
            ('NVDA', 'Technology', 'Semiconductors'),
            ('META', 'Technology', 'Social Media'),
            ('AMZN', 'Consumer Cyclical', 'E-Commerce'),
            ('JPM', 'Financial Services', 'Banking'),
            ('V', 'Financial Services', 'Payment Processing'),
            ('WMT', 'Consumer Defensive', 'Retail'),
        ]

        for ticker, sector, industry in sample_tickers:
            await conn.execute("""
                INSERT INTO config_lv3_targets (ticker, sector, industry, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (ticker) DO UPDATE
                SET sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry,
                    updated_at = NOW()
            """, ticker, sector, industry)

        print(f"✓ Seeded {len(sample_tickers)} target tickers")

        # Seed config_lv3_market_holidays (sample holidays)
        print("\nSeeding config_lv3_market_holidays...")
        today = datetime.now().date()
        holidays = [
            (today - timedelta(days=365), "New Year's Day 2024", True),
            (today - timedelta(days=300), "Memorial Day 2024", True),
            (today - timedelta(days=200), "Independence Day 2024", True),
            (today - timedelta(days=100), "Labor Day 2024", True),
            (today - timedelta(days=50), "Thanksgiving 2024", True),
            (today - timedelta(days=30), "Christmas 2024", True),
        ]

        for date, name, is_closed in holidays:
            await conn.execute("""
                INSERT INTO config_lv3_market_holidays (exchange, date, name, is_closed, is_fully_closed, updated_at)
                VALUES ('NASDAQ', $1, $2, $3, $3, NOW())
                ON CONFLICT (exchange, date) DO UPDATE
                SET name = EXCLUDED.name,
                    is_closed = EXCLUDED.is_closed,
                    updated_at = NOW()
            """, date, name, is_closed)

        print(f"✓ Seeded {len(holidays)} market holidays")

        # Seed sample txn_events for testing
        print("\nSeeding sample txn_events...")
        for ticker, sector, industry in sample_tickers[:5]:  # First 5 tickers
            event_date = today - timedelta(days=7)
            await conn.execute("""
                INSERT INTO txn_events (
                    ticker, event_date, sector, industry, source, source_id,
                    position_quantitative, disparity_quantitative,
                    position_qualitative, disparity_qualitative,
                    condition
                )
                VALUES ($1, $2, $3, $4, 'evt_consensus', $5, $6, $7, $8, $9, NULL)
                ON CONFLICT (ticker, event_date, source, source_id) DO NOTHING
            """, ticker, event_date, sector, industry, f"test_{ticker}_{event_date}",
                'long' if hash(ticker) % 2 == 0 else 'short',
                0.05 if hash(ticker) % 2 == 0 else -0.03,
                'long' if hash(ticker) % 3 == 0 else 'short',
                0.08 if hash(ticker) % 3 == 0 else -0.02)

        print("✓ Seeded sample transaction events")

        # Verify seeded data
        print("\n=== Verification ===")

        api_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv1_api_service")
        print(f"API services: {api_count}")

        target_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv3_targets")
        print(f"Target tickers: {target_count}")

        holiday_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv3_market_holidays")
        print(f"Market holidays: {holiday_count}")

        event_count = await conn.fetchval("SELECT COUNT(*) FROM txn_events")
        print(f"Transaction events: {event_count}")

        await conn.close()
        print("\n✓ Database seeding completed successfully!")

    except Exception as e:
        print(f"\n✗ Error seeding database: {e}")
        raise


if __name__ == "__main__":
    print("=== AlSign Database Seeding ===\n")
    asyncio.run(seed_database())
