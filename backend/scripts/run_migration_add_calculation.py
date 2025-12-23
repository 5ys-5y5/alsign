"""
Migration script: Add calculation column to config_lv2_metric_transform

Run this script to add the calculation column and populate it with existing transform logic.
"""

import asyncio
import asyncpg
import os
from pathlib import Path

# Database connection settings
SUPABASE_HOST = os.getenv("SUPABASE_HOST", "localhost")
SUPABASE_PORT = os.getenv("SUPABASE_PORT", "5432")
SUPABASE_DB = os.getenv("SUPABASE_DB", "postgres")
SUPABASE_USER = os.getenv("SUPABASE_USER", "postgres")
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD", "")

DATABASE_URL = f"postgresql://{SUPABASE_USER}:{SUPABASE_PASSWORD}@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DB}"


async def run_migration():
    """Run migration to add calculation column."""
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("Running migration: Add calculation column...")
        
        # Read migration SQL
        migration_file = Path(__file__).parent / "migrations" / "add_calculation_column.sql"
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        await conn.execute(migration_sql)
        print("✓ Migration completed: calculation column added")
        
        # Read seed SQL
        seed_file = Path(__file__).parent / "seed_calculation_codes.sql"
        if seed_file.exists():
            print("\nPopulating calculation codes...")
            with open(seed_file, 'r', encoding='utf-8') as f:
                seed_sql = f.read()
            
            await conn.execute(seed_sql)
            print("✓ Seed data populated")
        
        # Verify migration
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = 'config_lv2_metric_transform' "
            "AND column_name = 'calculation'"
        )
        
        if result > 0:
            print("\n✓ Verification: calculation column exists")
            
            # Count how many transforms have calculation codes
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM config_lv2_metric_transform WHERE calculation IS NOT NULL"
            )
            print(f"✓ {count} transform(s) have calculation codes")
        else:
            print("\n✗ Verification failed: calculation column not found")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())


