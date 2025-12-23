#!/usr/bin/env python3
"""
Test Supabase database connection.

This script verifies that the backend can successfully connect to Supabase
and execute basic queries.

Usage:
    python backend/scripts/test_supabase_connection.py
"""

import asyncio
import asyncpg
import sys
import os

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import settings


async def test_connection():
    """Test the Supabase database connection."""

    print("=" * 80)
    print("Supabase Connection Test")
    print("=" * 80)
    print()

    print(f"Testing connection to: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'hidden'}")
    print()

    try:
        # Test connection
        print("1. Attempting to connect...")
        conn = await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
        print("   ✓ Connection established")
        print()

        # Test database version
        print("2. Checking PostgreSQL version...")
        version = await conn.fetchval("SELECT version()")
        print(f"   ✓ {version.split(',')[0]}")
        print()

        # Test simple query
        print("3. Testing simple query...")
        result = await conn.fetchval("SELECT 1 + 1")
        print(f"   ✓ Query result: {result}")
        print()

        # Test schema access
        print("4. Checking database schema...")
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        if tables:
            print(f"   ✓ Found {len(tables)} tables:")
            for table in tables:
                print(f"     - {table['table_name']}")
        else:
            print("   ⚠ No tables found. Run setup_supabase.sql first.")
        print()

        # Test config_lv1_api_service table
        print("5. Testing config_lv1_api_service table...")
        try:
            api_services = await conn.fetch("SELECT api_service, \"usagePerMin\" FROM config_lv1_api_service")
            if api_services:
                print(f"   ✓ Found {len(api_services)} API services:")
                for svc in api_services:
                    print(f"     - {svc['api_service']}: {svc['usagePerMin']} calls/min")
            else:
                print("   ⚠ config_lv1_api_service table is empty")
        except asyncpg.exceptions.UndefinedTableError:
            print("   ⚠ config_lv1_api_service table not found. Run setup_supabase.sql first.")
        print()

        # Test write operation
        print("6. Testing write operation...")
        try:
            test_ticker = "TEST_CONNECTION"
            await conn.execute("""
                INSERT INTO config_lv3_targets (ticker, sector, industry, response_key)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (ticker) DO UPDATE
                SET sector = EXCLUDED.sector
            """, test_ticker, "Technology", "Testing", '{"test": true}')

            result = await conn.fetchrow(
                "SELECT * FROM config_lv3_targets WHERE ticker = $1",
                test_ticker
            )

            if result:
                print(f"   ✓ Write successful (ticker: {result['ticker']})")

                # Cleanup test data
                await conn.execute("DELETE FROM config_lv3_targets WHERE ticker = $1", test_ticker)
                print("   ✓ Cleanup successful")
            else:
                print("   ✗ Write operation failed")
        except asyncpg.exceptions.UndefinedTableError:
            print("   ⚠ config_lv3_targets table not found. Run setup_supabase.sql first.")
        except Exception as e:
            print(f"   ✗ Write operation failed: {e}")
        print()

        # Close connection
        await conn.close()
        print("=" * 80)
        print("✓ All connection tests passed!")
        print("=" * 80)

        return True

    except asyncpg.exceptions.InvalidPasswordError:
        print("\n✗ Connection failed: Invalid password")
        print("   Check DATABASE_URL in backend/.env")
        return False

    except asyncpg.exceptions.InvalidCatalogNameError:
        print("\n✗ Connection failed: Database does not exist")
        print("   Verify Supabase project is active")
        return False

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print()
    success = asyncio.run(test_connection())
    print()

    if success:
        print("Next steps:")
        print("1. If tables are missing, run: psql <DATABASE_URL> -f backend/scripts/setup_supabase.sql")
        print("   Or copy setup_supabase.sql content to Supabase SQL Editor")
        print("2. Update FMP_API_KEY in backend/.env")
        print("3. Start the backend: cd backend && uvicorn src.main:app --reload")
        print()
        sys.exit(0)
    else:
        print("Fix the connection error and try again.")
        print()
        sys.exit(1)
