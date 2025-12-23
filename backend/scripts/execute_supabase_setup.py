#!/usr/bin/env python3
"""
Execute Supabase database setup script.

This script attempts to execute the setup_supabase.sql file
on the configured Supabase database.

Usage:
    python backend/scripts/execute_supabase_setup.py
"""

import asyncio
import asyncpg
import sys
import os
from pathlib import Path

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.config import settings
    DATABASE_URL = settings.DATABASE_URL
except Exception as e:
    # Fallback if config can't be loaded
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:kVJ0kREfFUQGEy7F@db.fgypclaqxonwxlmqdphx.supabase.co:5432/postgres")

# Path to SQL script
SQL_SCRIPT_PATH = Path(__file__).parent / "setup_supabase.sql"


async def execute_sql_script():
    """Execute the setup_supabase.sql script."""

    print("=" * 80)
    print("AlSign Supabase Database Setup Execution")
    print("=" * 80)
    print()

    # Check if SQL script exists
    if not SQL_SCRIPT_PATH.exists():
        print(f"✗ ERROR: SQL script not found at {SQL_SCRIPT_PATH}")
        return False

    # Read SQL script
    print(f"Reading SQL script from: {SQL_SCRIPT_PATH.name}")
    with open(SQL_SCRIPT_PATH, 'r', encoding='utf-8') as f:
        sql_script = f.read()

    print(f"✓ Loaded SQL script ({len(sql_script)} characters)")
    print()

    # Extract connection info for display (hide password)
    conn_display = DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'configured database'
    print(f"Connecting to: {conn_display}")
    print()

    try:
        # Connect to database
        print("1. Attempting to connect to Supabase...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("   ✓ Connection established")
        print()

        # Execute SQL script
        print("2. Executing SQL script...")
        print("   This may take 10-30 seconds...")
        print()

        # Execute the script
        await conn.execute(sql_script)

        print("   ✓ SQL script executed successfully")
        print()

        # Verify tables created
        print("3. Verifying tables created...")
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        if len(tables) >= 11:
            print(f"   ✓ Found {len(tables)} tables:")
            for table in tables:
                print(f"     - {table['table_name']}")
        else:
            print(f"   ⚠ Only {len(tables)} tables found (expected 11+)")
        print()

        # Check seed data
        print("4. Verifying seed data...")
        api_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv1_api_service")
        policy_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv0_policy")
        target_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv3_targets")

        print(f"   - API services: {api_count}")
        print(f"   - Policies: {policy_count}")
        print(f"   - Target tickers: {target_count}")
        print()

        await conn.close()

        print("=" * 80)
        print("✓ DATABASE SETUP COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Add your FMP_API_KEY to backend/.env")
        print("2. Start backend: cd backend && uvicorn src.main:app --reload")
        print("3. Start frontend: cd frontend && npm run dev")
        print()

        return True

    except asyncpg.exceptions.InvalidPasswordError:
        print()
        print("=" * 80)
        print("✗ CONNECTION FAILED: Invalid password")
        print("=" * 80)
        print()
        print("The database password is incorrect.")
        print("Please check the DATABASE_URL in backend/.env")
        print()
        return False

    except asyncpg.exceptions.InvalidCatalogNameError:
        print()
        print("=" * 80)
        print("✗ CONNECTION FAILED: Database does not exist")
        print("=" * 80)
        print()
        print("The database 'postgres' does not exist on the server.")
        print("Please verify the Supabase project is active.")
        print()
        return False

    except (OSError, IOError, ConnectionError) as e:
        print()
        print("=" * 80)
        print("✗ CONNECTION FAILED: Cannot reach Supabase")
        print("=" * 80)
        print()
        print(f"Error: {e}")
        print()
        print("Possible causes:")
        print("1. Supabase project is PAUSED")
        print("2. Network connectivity issue")
        print("3. Incorrect database host")
        print()
        print("=" * 80)
        print("MANUAL EXECUTION REQUIRED")
        print("=" * 80)
        print()
        print("Please execute the SQL script manually:")
        print()
        print("1. Open Supabase Dashboard:")
        print("   https://app.supabase.com/project/fgypclaqxonwxlmqdphx")
        print()
        print("2. Verify project is ACTIVE (not paused)")
        print("   - If paused, click 'Resume' and wait 1-2 minutes")
        print()
        print("3. Go to SQL Editor → New query")
        print()
        print(f"4. Open file: {SQL_SCRIPT_PATH}")
        print("   - Select all content (Ctrl+A)")
        print("   - Copy (Ctrl+C)")
        print()
        print("5. Paste into Supabase SQL Editor")
        print()
        print("6. Click 'Run' button (or press F5)")
        print()
        print("7. Wait for completion (10-30 seconds)")
        print()
        print("8. Verify output shows:")
        print("   NOTICE: AlSign Database Setup Complete")
        print("   NOTICE: API services: 2")
        print("   NOTICE: Target tickers: 10")
        print()
        return False

    except Exception as e:
        print()
        print("=" * 80)
        print("✗ EXECUTION FAILED")
        print("=" * 80)
        print()
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")
        print()
        import traceback
        traceback.print_exc()
        print()
        return False


if __name__ == "__main__":
    print()
    success = asyncio.run(execute_sql_script())
    print()

    if not success:
        print("For detailed setup instructions, see:")
        print("- SUPABASE_SETUP.md")
        print("- QUICKSTART.md")
        print()
        sys.exit(1)
    else:
        sys.exit(0)
