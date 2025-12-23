#!/usr/bin/env python3
"""
Supabase database setup script for AlSign Financial Data API.

This script creates all database tables, types, functions, and seeds initial data.

Usage:
    python backend/scripts/setup_supabase.py
"""

import asyncio
import asyncpg
import os
from datetime import datetime

# Supabase connection details
# Try direct database connection instead of pooler
SUPABASE_PROJECT_REF = "fgypclaqxonwxlmqdphx"
SUPABASE_HOST = f"db.{SUPABASE_PROJECT_REF}.supabase.co"
SUPABASE_PORT = "5432"  # Direct connection uses 5432
SUPABASE_DB = "postgres"
SUPABASE_USER = "postgres"
SUPABASE_PASSWORD = "kVJ0kREfFUQGEy7F"

# Build connection string
DATABASE_URL = f"postgresql://{SUPABASE_USER}:{SUPABASE_PASSWORD}@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DB}"


async def setup_database():
    """Set up the complete Supabase database schema."""

    print("=" * 80)
    print("AlSign Supabase Database Setup")
    print("=" * 80)
    print()

    try:
        print(f"Connecting to Supabase...")
        conn = await asyncpg.connect(DATABASE_URL)
        print("✓ Connected to Supabase PostgreSQL")
        print()

        # Step 1: Create ENUM types
        print("Step 1: Creating ENUM types...")
        await conn.execute("""
            DO $$ BEGIN
                CREATE TYPE public.position AS ENUM ('long', 'short', 'neutral');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        print("  ✓ Created type: position")

        await conn.execute("""
            DO $$ BEGIN
                CREATE TYPE public.metric_source AS ENUM ('api_field', 'aggregation', 'expression');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        print("  ✓ Created type: metric_source")

        await conn.execute("""
            DO $$ BEGIN
                CREATE TYPE public.metric_transform_type AS ENUM ('aggregation', 'transformation');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        print("  ✓ Created type: metric_transform_type")
        print()

        # Step 2: Create trigger functions
        print("Step 2: Creating trigger functions...")

        # Function to validate metric API field
        await conn.execute("""
            CREATE OR REPLACE FUNCTION validate_metric_api_field()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.source = 'api_field' AND NEW.api_list_id IS NULL THEN
                    RAISE EXCEPTION 'api_list_id is required when source is api_field';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("  ✓ Created function: validate_metric_api_field()")

        # Function to populate metric response key
        await conn.execute("""
            CREATE OR REPLACE FUNCTION populate_metric_response_key()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.response_key IS NULL AND NEW.response_path IS NOT NULL THEN
                    NEW.response_key := to_jsonb(string_to_array(NEW.response_path, '.'));
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("  ✓ Created function: populate_metric_response_key()")

        # Function to update updated_at timestamp
        await conn.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("  ✓ Created function: update_updated_at_column()")
        print()

        # Step 3: Create config tables
        print("Step 3: Creating config tables...")

        # config_lv0_policy
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv0_policy (
                endpoint text NULL,
                function text NOT NULL,
                description text NULL,
                policy jsonb NULL,
                created_at timestamp with time zone NOT NULL DEFAULT NOW(),
                CONSTRAINT config_lv0_policy_pkey PRIMARY KEY (function)
            );
        """)
        print("  ✓ Created table: config_lv0_policy")

        # config_lv1_api_service
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv1_api_service (
                created_at timestamp with time zone NOT NULL DEFAULT NOW(),
                api_service text NOT NULL,
                "apiKey" text NULL,
                "usagePerMin" integer NULL,
                CONSTRAINT config_api_service_pkey PRIMARY KEY (api_service)
            );
        """)
        print("  ✓ Created table: config_lv1_api_service")

        # config_lv1_api_list
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv1_api_list (
                id text NOT NULL,
                api_service text NULL,
                api text NULL,
                schema jsonb NULL,
                endpoint text NULL,
                function2 text NULL,
                created_at timestamp with time zone NULL DEFAULT NOW(),
                CONSTRAINT config_api_list_pkey PRIMARY KEY (id),
                CONSTRAINT config_api_list_api_service_fkey FOREIGN KEY (api_service)
                    REFERENCES config_lv1_api_service (api_service)
            );
        """)
        print("  ✓ Created table: config_lv1_api_list")

        # config_lv2_metric_transform
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv2_metric_transform (
                id text NOT NULL,
                transform_type public.metric_transform_type NOT NULL DEFAULT 'aggregation'::metric_transform_type,
                description text NOT NULL,
                input_kind text NOT NULL,
                output_kind text NOT NULL,
                params_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
                example_params jsonb NOT NULL DEFAULT '{}'::jsonb,
                version integer NOT NULL DEFAULT 1,
                is_active boolean NOT NULL DEFAULT true,
                created_at timestamp with time zone NULL DEFAULT NOW(),
                CONSTRAINT config_lv1_metric_transform_pkey PRIMARY KEY (id)
            );
        """)
        print("  ✓ Created table: config_lv2_metric_transform")

        # config_lv2_metric
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv2_metric (
                id text NOT NULL,
                description text NULL,
                source public.metric_source NOT NULL,
                api_list_id text NULL,
                base_metric_id text NULL,
                aggregation_kind text NULL,
                aggregation_params jsonb NULL DEFAULT '{}'::jsonb,
                expression text NULL,
                domain text NULL,
                created_at timestamp with time zone NULL DEFAULT NOW(),
                response_path text NULL,
                response_key jsonb NULL,
                CONSTRAINT config_lv2_metric_pkey PRIMARY KEY (id),
                CONSTRAINT config_lv2_metric_api_list_id_fkey FOREIGN KEY (api_list_id)
                    REFERENCES config_lv1_api_list (id) ON UPDATE CASCADE ON DELETE CASCADE,
                CONSTRAINT config_lv2_metric_base_metric_id_fkey FOREIGN KEY (base_metric_id)
                    REFERENCES config_lv2_metric (id),
                CONSTRAINT fk_metric_aggregation_kind FOREIGN KEY (aggregation_kind)
                    REFERENCES config_lv2_metric_transform (id),
                CONSTRAINT config_lv2_metric_source_consistency_check CHECK (
                    (
                        (source = 'api_field'::metric_source AND api_list_id IS NOT NULL AND response_key IS NOT NULL)
                        OR (source = 'aggregation'::metric_source AND base_metric_id IS NOT NULL AND aggregation_kind IS NOT NULL)
                        OR (source = 'expression'::metric_source AND expression IS NOT NULL)
                    )
                )
            );
        """)
        print("  ✓ Created table: config_lv2_metric")

        # Create index on config_lv2_metric
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_config_lv2_metric_sort_desc
            ON public.config_lv2_metric USING btree (source DESC, api_list_id DESC, created_at DESC);
        """)
        print("  ✓ Created index: idx_config_lv2_metric_sort_desc")

        # Create triggers on config_lv2_metric
        await conn.execute("""
            DROP TRIGGER IF EXISTS trg_validate_metric_api_field ON config_lv2_metric;
            CREATE TRIGGER trg_validate_metric_api_field
            BEFORE INSERT OR UPDATE ON config_lv2_metric
            FOR EACH ROW EXECUTE FUNCTION validate_metric_api_field();
        """)
        print("  ✓ Created trigger: trg_validate_metric_api_field")

        await conn.execute("""
            DROP TRIGGER IF EXISTS trg_populate_metric_response_key ON config_lv2_metric;
            CREATE TRIGGER trg_populate_metric_response_key
            BEFORE INSERT OR UPDATE ON config_lv2_metric
            FOR EACH ROW EXECUTE FUNCTION populate_metric_response_key();
        """)
        print("  ✓ Created trigger: trg_populate_metric_response_key")

        # config_lv3_market_holidays
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv3_market_holidays (
                exchange text NOT NULL,
                date date NOT NULL,
                name text NULL,
                is_closed boolean NULL,
                adj_open_time text NULL,
                adj_close_time text NULL,
                is_fully_closed boolean NULL,
                updated_at timestamp with time zone NULL DEFAULT NOW(),
                CONSTRAINT config_lv3_market_holidays_pkey PRIMARY KEY (exchange, date)
            );
        """)
        print("  ✓ Created table: config_lv3_market_holidays")

        # Create trigger for updated_at on market_holidays
        await conn.execute("""
            DROP TRIGGER IF EXISTS trg_update_market_holidays_updated_at ON config_lv3_market_holidays;
            CREATE TRIGGER trg_update_market_holidays_updated_at
            BEFORE UPDATE ON config_lv3_market_holidays
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("  ✓ Created trigger: trg_update_market_holidays_updated_at")

        # config_lv3_targets
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv3_targets (
                id uuid NOT NULL DEFAULT gen_random_uuid(),
                ticker text NOT NULL,
                sector text NULL,
                industry text NULL,
                response_key jsonb NOT NULL,
                updated_at timestamp without time zone NULL DEFAULT NOW(),
                CONSTRAINT config_lv3_targets_pkey PRIMARY KEY (ticker)
            );
        """)
        print("  ✓ Created table: config_lv3_targets")

        # Create trigger for updated_at on targets
        await conn.execute("""
            DROP TRIGGER IF EXISTS trg_update_targets_updated_at ON config_lv3_targets;
            CREATE TRIGGER trg_update_targets_updated_at
            BEFORE UPDATE ON config_lv3_targets
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("  ✓ Created trigger: trg_update_targets_updated_at")

        # config_lv3_analyst
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.config_lv3_analyst (
                id uuid NOT NULL DEFAULT gen_random_uuid(),
                analyst_name text NULL,
                analyst_company text NULL,
                analyst_name_key text GENERATED ALWAYS AS (COALESCE(analyst_name, '__NULL__')) STORED,
                analyst_company_key text GENERATED ALWAYS AS (COALESCE(analyst_company, '__NULL__')) STORED,
                performance jsonb NOT NULL,
                updated_at timestamp without time zone NULL DEFAULT NOW(),
                CONSTRAINT config_lv3_analyst_pkey PRIMARY KEY (id),
                CONSTRAINT config_lv3_analyst_uniq_key UNIQUE (analyst_name_key, analyst_company_key)
            );
        """)
        print("  ✓ Created table: config_lv3_analyst")

        # Create trigger for updated_at on analyst
        await conn.execute("""
            DROP TRIGGER IF EXISTS trg_update_analyst_updated_at ON config_lv3_analyst;
            CREATE TRIGGER trg_update_analyst_updated_at
            BEFORE UPDATE ON config_lv3_analyst
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)
        print("  ✓ Created trigger: trg_update_analyst_updated_at")
        print()

        # Step 4: Create event tables
        print("Step 4: Creating event tables...")

        # evt_consensus
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.evt_consensus (
                id uuid NOT NULL DEFAULT gen_random_uuid(),
                ticker text NOT NULL,
                event_date timestamp with time zone NOT NULL,
                analyst_name text NULL,
                analyst_company text NULL,
                price_target numeric NULL,
                price_when_posted numeric NULL,
                price_target_prev numeric NULL,
                price_when_posted_prev numeric NULL,
                direction text NULL,
                response_key jsonb NULL,
                created_at timestamp with time zone NOT NULL DEFAULT NOW(),
                CONSTRAINT evt_consensus_pkey PRIMARY KEY (id),
                CONSTRAINT evt_consensus_unique_news UNIQUE (ticker, event_date, analyst_name, analyst_company)
            );
        """)
        print("  ✓ Created table: evt_consensus")

        # evt_earning
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.evt_earning (
                id uuid NOT NULL DEFAULT gen_random_uuid(),
                ticker text NOT NULL,
                event_date timestamp with time zone NOT NULL,
                response_key jsonb NULL,
                created_at timestamp with time zone NOT NULL DEFAULT NOW(),
                CONSTRAINT evt_earning_pkey PRIMARY KEY (id),
                CONSTRAINT evt_earning_unique UNIQUE (ticker, event_date)
            );
        """)
        print("  ✓ Created table: evt_earning")
        print()

        # Step 5: Create transaction table
        print("Step 5: Creating transaction table...")

        # txn_events
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.txn_events (
                id uuid NOT NULL DEFAULT gen_random_uuid(),
                ticker text NOT NULL,
                event_date timestamp with time zone NOT NULL,
                sector text NULL,
                industry text NULL,
                source text NOT NULL,
                source_id text NOT NULL,
                value_quantitative jsonb NULL,
                position_quantitative public.position NULL,
                disparity_quantitative numeric NULL,
                value_qualitative jsonb NULL,
                position_qualitative public.position NULL,
                disparity_qualitative numeric NULL,
                price_trend jsonb NULL,
                analyst_performance jsonb NULL,
                condition text NULL,
                created_at timestamp with time zone NOT NULL DEFAULT NOW(),
                CONSTRAINT txn_events_pkey PRIMARY KEY (id),
                CONSTRAINT txn_events_uniq UNIQUE (ticker, event_date, source, source_id)
            );
        """)
        print("  ✓ Created table: txn_events")
        print()

        # Step 6: Seed initial data
        print("Step 6: Seeding initial data...")

        # Seed API services
        await conn.execute("""
            INSERT INTO public.config_lv1_api_service (api_service, "apiKey", "usagePerMin")
            VALUES
                ('financialmodelingprep', NULL, 300),
                ('internal', NULL, NULL)
            ON CONFLICT (api_service) DO UPDATE
            SET "usagePerMin" = EXCLUDED."usagePerMin";
        """)
        print("  ✓ Seeded API services (financialmodelingprep, internal)")

        # Seed sample policies
        await conn.execute("""
            INSERT INTO public.config_lv0_policy (endpoint, function, description, policy)
            VALUES
                ('fillPriceTrend', 'fillPriceTrend_dateRange',
                 'Price history collection range for endpoint',
                 '{"countEnd":14,"countStart":-14}'::jsonb)
            ON CONFLICT (function) DO UPDATE
            SET endpoint = EXCLUDED.endpoint,
                description = EXCLUDED.description,
                policy = EXCLUDED.policy;
        """)
        print("  ✓ Seeded sample policies")

        # Seed sample targets
        sample_tickers = [
            ('AAPL', 'Technology', 'Consumer Electronics'),
            ('MSFT', 'Technology', 'Software'),
            ('GOOGL', 'Technology', 'Internet Services'),
            ('TSLA', 'Automotive', 'Electric Vehicles'),
            ('NVDA', 'Technology', 'Semiconductors'),
        ]

        for ticker, sector, industry in sample_tickers:
            await conn.execute("""
                INSERT INTO config_lv3_targets (ticker, sector, industry, response_key)
                VALUES ($1, $2, $3, '{}'::jsonb)
                ON CONFLICT (ticker) DO UPDATE
                SET sector = EXCLUDED.sector,
                    industry = EXCLUDED.industry;
            """, ticker, sector, industry)

        print(f"  ✓ Seeded {len(sample_tickers)} sample target tickers")
        print()

        # Verify setup
        print("=" * 80)
        print("Verification")
        print("=" * 80)

        api_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv1_api_service")
        print(f"API services: {api_count}")

        policy_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv0_policy")
        print(f"Policies: {policy_count}")

        target_count = await conn.fetchval("SELECT COUNT(*) FROM config_lv3_targets")
        print(f"Target tickers: {target_count}")

        # List all tables
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        print(f"\nTotal tables created: {len(tables)}")
        for table in tables:
            print(f"  - {table['table_name']}")

        await conn.close()
        print()
        print("=" * 80)
        print("✓ Supabase database setup completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Error during database setup: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(setup_database())
