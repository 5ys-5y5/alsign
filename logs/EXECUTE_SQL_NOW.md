# ⚡ Execute SQL Script NOW - Step by Step

## ✅ Pre-Verification Complete

I have verified the SQL script against the guideline file (`1_guideline(tableSetting).ini`) and made necessary corrections:

- ✅ Fixed `usagePerMin` data type (integer → smallint)
- ✅ Verified all 11 tables match guideline structure
- ✅ Verified ENUM types and trigger functions
- ✅ Removed sensitive API keys from seed data
- ✅ SQL script is ready to execute

**SQL Script Location**: `backend/scripts/setup_supabase.sql`

---

## 🚨 Cannot Connect Programmatically

**Error**: `[Errno 11001] getaddrinfo failed`

**Reason**: Supabase project is likely PAUSED or network issue

**Solution**: Execute SQL manually via Supabase Dashboard (5 minutes)

---

## 📋 Manual Execution Steps

### Step 1: Open Supabase Dashboard

Click this link or paste in browser:
```
https://app.supabase.com/project/fgypclaqxonwxlmqdphx
```

### Step 2: Check Project Status

Look at the top-right corner of the dashboard:

- ✅ **Status: Active** → Continue to Step 3
- ⏸️ **Status: Paused** → Click **"Resume"** button, wait 1-2 minutes, then continue

### Step 3: Open SQL Editor

In the left sidebar:
1. Click **"SQL Editor"**
2. Click **"New query"** button (green button)

### Step 4: Copy SQL Script

On your computer:
1. Open file: `C:\Users\GY\Downloads\alsign\alsign\backend\scripts\setup_supabase.sql`
2. Select ALL content:
   - **Windows**: `Ctrl+A`
   - **Mac**: `Cmd+A`
3. Copy:
   - **Windows**: `Ctrl+C`
   - **Mac**: `Cmd+C`

### Step 5: Paste and Execute

In Supabase SQL Editor:
1. Click in the editor area
2. Paste:
   - **Windows**: `Ctrl+V`
   - **Mac**: `Cmd+V`
3. Click **"Run"** button (bottom right) or press **F5**

### Step 6: Wait for Completion

You should see:
```
NOTICE:  ============================================================
NOTICE:  AlSign Database Setup Complete
NOTICE:  ============================================================
NOTICE:  API services: 2
NOTICE:  Policies: 1
NOTICE:  Target tickers: 10
NOTICE:  Total tables created: 11
NOTICE:  ============================================================
```

Plus a table listing all created tables.

**Execution time**: ~10-30 seconds

### Step 7: Verify Tables

Go to **Table Editor** (left sidebar) and confirm these 11 tables exist:

- [ ] config_lv0_policy
- [ ] config_lv1_api_service
- [ ] config_lv1_api_list
- [ ] config_lv2_metric
- [ ] config_lv2_metric_transform
- [ ] config_lv3_market_holidays
- [ ] config_lv3_targets
- [ ] config_lv3_analyst
- [ ] evt_consensus
- [ ] evt_earning
- [ ] txn_events

---

## ✅ After Successful Execution

Once you see the success message:

### 1. Test Database Connection

Open new terminal:
```bash
cd backend
python scripts/test_supabase_connection.py
```

**Expected output**:
```
✓ Connection established
✓ PostgreSQL 15.x
✓ Query result: 2
✓ Found 11 tables
✓ All connection tests passed!
```

### 2. Start Backend Server

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output**:
```
INFO:     Starting application...
INFO:     Database connection pool created
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 3. Verify Backend Health

Open browser or new terminal:
```bash
curl http://localhost:8000/health
```

**Expected response**:
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Connected"
    }
  }
}
```

### 4. Access Full Application

- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:3001 (already running)

---

## 🎉 Success!

Once all 3 services are running, you'll have:

✅ **Database** - Supabase PostgreSQL with 11 tables
✅ **Backend** - FastAPI on port 8000
✅ **Frontend** - React on port 3001

**Complete system ready!** 🚀

---

## ⚠️ Troubleshooting

### If SQL execution fails

**Error**: `relation already exists`
- **Solution**: Script is idempotent, this is OK. Check if tables exist in Table Editor.

**Error**: `permission denied`
- **Solution**: Ensure you're logged in as project owner in Supabase.

**Error**: `syntax error`
- **Solution**: Ensure you copied the ENTIRE SQL script (14,079 characters).

### If backend still won't start

1. Verify Supabase project is **Active** (not paused)
2. Wait 2-3 minutes after resuming project
3. Check DATABASE_URL in `backend/.env` matches project
4. Try connection test again: `python scripts/test_supabase_connection.py`

### Need help?

- **Detailed guide**: [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md)
- **Quick start**: [`QUICKSTART.md`](QUICKSTART.md)
- **Frontend docs**: [`frontend/README.md`](frontend/README.md)

---

## 📊 What This Script Creates

### ENUM Types (3)
- `position` - long, short, neutral
- `metric_source` - api_field, aggregation, expression
- `metric_transform_type` - aggregation, transformation

### Trigger Functions (3)
- `validate_metric_api_field()` - Validates metric configuration
- `populate_metric_response_key()` - Auto-populates response keys
- `update_updated_at_column()` - Auto-updates timestamps

### Tables (11)
- **Config Level 0**: policy
- **Config Level 1**: api_service, api_list
- **Config Level 2**: metric, metric_transform
- **Config Level 3**: market_holidays, targets, analyst
- **Events**: evt_consensus, evt_earning
- **Transactions**: txn_events

### Seed Data
- 2 API services (financialmodelingprep, internal)
- 1 policy (fillPriceTrend_dateRange)
- 10 sample target tickers (AAPL, MSFT, GOOGL, TSLA, NVDA, META, AMZN, JPM, V, WMT)

---

## 🎯 Current Status

| Component | Status |
|-----------|--------|
| **SQL Script** | ✅ Verified & Ready |
| **Database Connection** | ⏳ Awaiting Activation |
| **Backend Server** | ⏳ Waiting for DB |
| **Frontend Server** | ✅ Running (port 3001) |

**Next Action**: Execute SQL script manually (Steps 1-7 above)

Time required: **5 minutes**
