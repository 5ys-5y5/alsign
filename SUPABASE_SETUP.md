# Supabase Setup Guide

This guide explains how to configure and connect the AlSign backend to Supabase PostgreSQL.

## Current Status

✅ **Configuration Updated**:
- Backend `.env` file created with Supabase credentials
- Database connection pool configured for SSL
- Test scripts created

⏳ **Action Required**:
- Execute database schema setup in Supabase SQL Editor
- Verify Supabase project is active and accessible

---

## Step 1: Verify Supabase Project Status

### Check Project Availability

1. **Open Supabase Dashboard**
   - URL: https://app.supabase.com/project/fgypclaqxonwxlmqdphx
   - Login with your Supabase account

2. **Check Project Status**
   - Verify the project is **Active** (not paused)
   - If paused, click "Resume" to activate the project
   - Wait 1-2 minutes for the database to become available

3. **Get Connection Details**
   - Go to **Settings** → **Database**
   - Note the connection details:
     - **Host**: `db.fgypclaqxonwxlmqdphx.supabase.co`
     - **Port**: `5432` (direct) or `6543` (pooler)
     - **Database**: `postgres`
     - **User**: `postgres`
     - **Password**: (already configured)

---

## Step 2: Execute Database Schema Setup

### Option A: Using Supabase SQL Editor (Recommended)

1. **Open SQL Editor**
   - In Supabase Dashboard, go to **SQL Editor**
   - Click **New query**

2. **Copy Schema Script**
   - Open: `backend/scripts/setup_supabase.sql`
   - Copy entire file content (Ctrl+A, Ctrl+C)

3. **Execute Script**
   - Paste into SQL Editor
   - Click **Run** button (or press F5)
   - Wait for execution to complete (~5-10 seconds)

4. **Verify Results**
   - Check the output panel at bottom
   - Should see messages indicating successful table creation
   - Verify message: "AlSign Database Setup Complete"

5. **Confirm Tables Created**
   - Go to **Table Editor** in left menu
   - Should see 11 tables:
     - `config_lv0_policy`
     - `config_lv1_api_service`
     - `config_lv1_api_list`
     - `config_lv2_metric`
     - `config_lv2_metric_transform`
     - `config_lv3_market_holidays`
     - `config_lv3_targets`
     - `config_lv3_analyst`
     - `evt_consensus`
     - `evt_earning`
     - `txn_events`

### Option B: Using psql Command Line

```bash
# Install psql if not already installed (PostgreSQL client)
# Windows: Download from https://www.postgresql.org/download/windows/
# Mac: brew install postgresql
# Linux: sudo apt-get install postgresql-client

# Run schema setup
psql "postgresql://postgres:kVJ0kREfFUQGEy7F@db.fgypclaqxonwxlmqdphx.supabase.co:5432/postgres" \
  -f backend/scripts/setup_supabase.sql
```

### Option C: Using Python Script (if connection works)

```bash
cd backend
python scripts/setup_supabase.py
```

---

## Step 3: Test Backend Connection

### Update FMP API Key

Before testing, add your Financial Modeling Prep API key to `backend/.env`:

```env
FMP_API_KEY=your_actual_fmp_api_key_here
```

Get an API key from: https://financialmodelingprep.com/developer/docs/

### Run Connection Test

```bash
cd backend
python scripts/test_supabase_connection.py
```

**Expected Output**:
```
================================================================================
Supabase Connection Test
================================================================================

Testing connection to: db.fgypclaqxonwxlmqdphx.supabase.co:5432/postgres

1. Attempting to connect...
   ✓ Connection established

2. Checking PostgreSQL version...
   ✓ PostgreSQL 15.x

3. Testing simple query...
   ✓ Query result: 2

4. Checking database schema...
   ✓ Found 11 tables:
     - config_lv0_policy
     - config_lv1_api_list
     ...

5. Testing config_lv1_api_service table...
   ✓ Found 2 API services:
     - financialmodelingprep: 300 calls/min
     - internal: None calls/min

6. Testing write operation...
   ✓ Write successful (ticker: TEST_CONNECTION)
   ✓ Cleanup successful

================================================================================
✓ All connection tests passed!
================================================================================
```

---

## Step 4: Start the Backend Server

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output**:
```
INFO:     Starting application...
INFO:     Database connection pool created
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Verify Health Endpoint

Open browser or use curl:
```bash
curl http://localhost:8000/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-12-18T...",
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Connected",
      "details": {
        "pool_size": 10,
        "pool_max_size": 20
      }
    }
  }
}
```

---

## Troubleshooting

### Error: "getaddrinfo failed" or "Tenant or user not found"

**Cause**: Supabase project is paused or not accessible

**Solution**:
1. Go to Supabase Dashboard
2. Check project status (top right corner)
3. If paused, click "Resume" and wait 1-2 minutes
4. Try connection test again

### Error: "Invalid password"

**Cause**: Database password in `.env` is incorrect

**Solution**:
1. Go to Supabase Dashboard → **Settings** → **Database**
2. Reset database password if needed
3. Update `DATABASE_URL` in `backend/.env`
4. Restart backend server

### Error: "SSL connection required"

**Cause**: Missing SSL configuration

**Solution**: Already configured in `backend/src/database/connection.py`. Ensure using `postgresql://` (not `postgres://`) in DATABASE_URL.

### Error: "Too many connections"

**Cause**: Connection pool exhausted

**Solution**: Use Supabase connection pooler instead:

Update `backend/.env`:
```env
DATABASE_URL=postgresql://postgres.fgypclaqxonwxlmqdphx:kVJ0kREfFUQGEy7F@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
```

### Tables Not Found

**Cause**: Schema setup not executed

**Solution**: Follow **Step 2** above to execute `setup_supabase.sql`

---

## Connection String Formats

### Direct Connection (Development)
- **Best for**: Local development, low connection count
- **Format**: `postgresql://postgres:PASSWORD@db.PROJECT_REF.supabase.co:5432/postgres`
- **Current**: `postgresql://postgres:kVJ0kREfFUQGEy7F@db.fgypclaqxonwxlmqdphx.supabase.co:5432/postgres`

### Connection Pooler (Production)
- **Best for**: Production, high connection count, serverless functions
- **Format**: `postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres`
- **Current**: `postgresql://postgres.fgypclaqxonwxlmqdphx:kVJ0kREfFUQGEy7F@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres`

---

## Environment Variables Reference

All environment variables are configured in `backend/.env`:

| Variable | Description | Current Value |
|----------|-------------|---------------|
| `DATABASE_URL` | PostgreSQL connection string | Supabase connection |
| `DB_POOL_MIN_SIZE` | Minimum connection pool size | 10 |
| `DB_POOL_MAX_SIZE` | Maximum connection pool size | 20 |
| `FMP_API_KEY` | Financial Modeling Prep API key | **TODO: Add your key** |
| `FMP_BASE_URL` | FMP API base URL | https://financialmodelingprep.com/api/v3 |
| `FMP_RATE_LIMIT` | API rate limit (calls/min) | 250 |
| `LOG_LEVEL` | Logging level | INFO |
| `ENVIRONMENT` | Runtime environment | development |
| `CORS_ORIGINS` | Allowed CORS origins | localhost:3000, localhost:5173 |

---

## Next Steps

Once the connection test passes:

1. ✅ Database schema created
2. ✅ Backend configured for Supabase
3. ⏭️ Add FMP API key to `backend/.env`
4. ⏭️ Start backend server
5. ⏭️ Test API endpoints using interactive docs at http://localhost:8000/docs
6. ⏭️ Set up frontend (see `frontend/README.md`)

---

## Files Updated

- ✅ `backend/.env` - Supabase credentials configured
- ✅ `backend/.env.example` - Updated with Supabase connection examples
- ✅ `backend/src/database/connection.py` - Added SSL support and application_name
- ✅ `backend/scripts/setup_supabase.sql` - Complete database schema
- ✅ `backend/scripts/test_supabase_connection.py` - Connection test script

---

## Support

For Supabase-specific issues:
- Documentation: https://supabase.com/docs/guides/database/connecting-to-postgres
- Dashboard: https://app.supabase.com/project/fgypclaqxonwxlmqdphx

For AlSign application issues:
- Check `/health` endpoint
- Review logs in terminal
- Consult API docs at `/docs`
