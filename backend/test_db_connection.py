"""Test database connection with asyncpg."""
import asyncio
import asyncpg


async def test_connection():
    """Test direct connection to database."""
    database_url = "postgresql://postgres.fgypclaqxonwxlmqdphx:qycKXqvs%40%21Q_Pt3@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

    print(f"Testing connection to database...")
    print(f"Python version: {asyncio.sys.version}")

    try:
        # Try creating a connection pool
        pool = await asyncpg.create_pool(
            dsn=database_url,
            min_size=1,
            max_size=2,
            timeout=30,
            statement_cache_size=0,
            command_timeout=30
        )
        print("✓ Connection pool created successfully")

        # Test a simple query
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            print(f"✓ Query test successful: {result}")

        await pool.close()
        print("✓ Connection closed successfully")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_connection())
