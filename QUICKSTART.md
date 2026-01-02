# AlSign Quick Start Guide

Complete setup guide for the AlSign Financial Data API system.

## Overview

This guide will help you set up the complete AlSign system:
1. ✅ **Backend** - FastAPI service (port 8000)
2. ✅ **Frontend** - React application (port 3000)
3. ✅ **Database** - Supabase PostgreSQL

**Estimated time**: 15-20 minutes

---

## Prerequisites

Before starting, ensure you have:

- [x] **Python 3.11+** installed ([Download](https://www.python.org/downloads/))
- [x] **Node.js 18+** installed ([Download](https://nodejs.org/))
- [x] **Supabase account** ([Sign up](https://supabase.com))
- [x] **FMP API key** ([Get free key](https://financialmodelingprep.com/developer/docs/))

---

## Step 1: Database Setup (5 minutes)

### 1.1 Verify Supabase Project

1. Open Supabase Dashboard: https://app.supabase.com/project/fgypclaqxonwxlmqdphx
2. Ensure project is **Active** (not paused)
3. If paused, click "Resume" and wait 1-2 minutes

### 1.2 Create Database Schema

1. In Supabase Dashboard, go to **SQL Editor**
2. Click **New query**
3. Open `backend/scripts/setup_supabase.sql` in your editor
4. Copy entire file content
5. Paste into SQL Editor
6. Click **Run** (or press F5)
7. Wait for completion (~5-10 seconds)

### 1.3 Verify Tables Created

Go to **Table Editor** and verify these 11 tables exist:
- ✅ `config_lv0_policy`
- ✅ `config_lv1_api_service`
- ✅ `config_lv1_api_list`
- ✅ `config_lv2_metric`
- ✅ `config_lv2_metric_transform`
- ✅ `config_lv3_market_holidays`
- ✅ `config_lv3_targets`
- ✅ `config_lv3_analyst`
- ✅ `evt_consensus`
- ✅ `evt_earning`
- ✅ `txn_events`

**Troubleshooting**: See [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md) for detailed help.

---

## Step 2: Backend Setup (5 minutes)

### 2.1 Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

**Expected output**: Successfully installed 20+ packages (fastapi, uvicorn, asyncpg, etc.)

### 2.2 Configure Environment

The `.env` file is **already created** with Supabase credentials.

**Action required**: Add your FMP API key

Edit `backend/.env`:
```env
FMP_API_KEY=your_actual_api_key_here
```

Get your API key from: https://financialmodelingprep.com/developer/docs/

### 2.3 Test Database Connection

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

**If connection fails**: Check [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md) troubleshooting section.

### 2.4 Start Backend Server

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output**:
```
INFO:     Starting application...
INFO:     Database connection pool created
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2.5 Verify Backend Health

Open in browser or use curl:
```bash
curl http://localhost:8000/health
```

**Expected response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-12-18T...",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Connected"
    }
  }
}
```

**Interactive API docs**: http://localhost:8000/docs

---

## Step 3: Frontend Setup (5 minutes)

### 3.1 Install Node Dependencies

Open **new terminal** (keep backend running):

```bash
cd frontend
npm install
```

**Expected output**: Added 273 packages (~20-30 seconds)

### 3.2 Configure Environment

The `.env` file is **already created** and points to `http://localhost:8000`.

No changes needed for local development.

For production, edit `frontend/.env`:
```env
VITE_API_BASE_URL=https://your-production-backend.com
```

### 3.3 Start Frontend Dev Server

```bash
cd frontend
npm run dev
```

**Expected output**:
```
VITE v5.4.21  ready in 683 ms

➜  Local:   http://localhost:3000/
```

### 3.4 Access Application

Open browser:
- **Frontend**: http://localhost:3000
- **Backend API docs**: http://localhost:8000/docs

---

## Step 4: Verify System (2 minutes)

### 4.1 Check Frontend Routes

Navigate to each route and verify page loads:

1. **Control** - http://localhost:3000/#/control
   - Should show API service configuration panel
   - Should show runtime info

2. **Requests** - http://localhost:3000/#/requests
   - Should show API request forms
   - Try "GET /health" request

3. **Condition Groups** - http://localhost:3000/#/conditionGroup
   - Should show condition group form

4. **Dashboard** - http://localhost:3000/#/dashboard
   - Should show KPI cards (may be empty initially)
   - Should show performance table

### 4.2 Test API Integration

From Frontend → Requests page:

1. Click **"GET /health"** form
2. Click **Execute** button
3. Verify response appears with `"status": "healthy"`

### 4.3 Test Data Flow (Optional)

1. Go to **Requests** page
2. Select **"GET /sourceData"** form
3. Set `mode` to `target`
4. Click **Execute**
5. Should fetch and store sample target tickers

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   User Browser                          │
│           http://localhost:3000                         │
└──────────────────┬──────────────────────────────────────┘
                   │ API Requests
                   ↓
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend                            │
│           http://localhost:8000                         │
│  - Source Data Collection (GET /sourceData)             │
│  - Event Processing (POST /setEventsTable)              │
│  - Dashboard APIs (GET /dashboard/*)                    │
└──────────────────┬──────────────────────────────────────┘
                   │ SQL Queries
                   ↓
┌─────────────────────────────────────────────────────────┐
│          Supabase PostgreSQL                            │
│  db.fgypclaqxonwxlmqdphx.supabase.co:5432               │
│  - 11 tables (config, events, transactions)             │
│  - Triggers, generated columns                          │
└─────────────────────────────────────────────────────────┘
```

---

## Common Issues

### Backend won't start

**Error**: `ModuleNotFoundError: No module named 'fastapi'`

**Solution**:
```bash
cd backend
pip install -r requirements.txt
```

### Frontend won't start

**Error**: `Cannot find module 'react'`

**Solution**:
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### CORS errors in browser

**Error**: `Access to fetch ... has been blocked by CORS policy`

**Solution**: Ensure backend `CORS_ORIGINS` includes `http://localhost:3000`:

Edit `backend/.env`:
```env
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Restart backend server.

### Database connection failed

**Error**: `Connection failed: [Errno 11001] getaddrinfo failed`

**Solutions**:
1. Verify Supabase project is active (not paused)
2. Check `DATABASE_URL` in `backend/.env`
3. See detailed troubleshooting in [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md)

---

## Next Steps

### 1. Populate Initial Data

Run data collection to populate tables:

```bash
# In Requests page UI, or via curl:
curl "http://localhost:8000/sourceData?mode=holiday"
curl "http://localhost:8000/sourceData?mode=target"
curl "http://localhost:8000/sourceData?mode=consensus"
```

#### Consensus Phase 2 Recalculation (calc_mode)

If evt_consensus already has data but `price_target_prev`/`direction` are NULL, run Phase 2 calculation only (no API calls):

```bash
# Recalculate all partitions (API 호출 없이 2단계 계산만 수행)
curl "http://localhost:8000/sourceData?mode=consensus&calc_mode=calculation&calc_scope=all"

# Recalculate specific tickers
curl "http://localhost:8000/sourceData?mode=consensus&calc_mode=calculation&calc_scope=ticker&tickers=RGTI,AAPL"
```

| calc_mode | Description |
|-----------|-------------|
| (unset) | Phase 1 (API fetch) + Phase 2 for affected partitions |
| `maintenance` | Phase 1 + Phase 2 with custom scope |
| `calculation` | **Phase 2 only** (skip API calls, use existing data) |

### 2. Explore API Endpoints

Visit interactive docs: http://localhost:8000/docs

Try these endpoints:
- **GET /sourceData** - Collect market data
- **POST /setEventsTable** - Consolidate events
- **POST /backfillEventsTable** - Calculate valuations
- **GET /dashboard/kpis** - View dashboard metrics
- **GET /dashboard/performanceSummary** - View event data

### 3. View Dashboard

After populating data:
1. Go to http://localhost:3000/#/dashboard
2. View KPI cards with metrics
3. Explore performance table with filters

### 4. Create Condition Groups

1. Go to http://localhost:3000/#/conditionGroup
2. Create a condition group (e.g., filter by sector="Technology")
3. Use in dashboard filters

---

## Development Workflow

### Running Both Services

You need **two terminal windows**:

**Terminal 1 - Backend**:
```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend**:
```bash
cd frontend
npm run dev
```

### Making Changes

- **Backend changes**: Uvicorn auto-reloads on file save
- **Frontend changes**: Vite HMR updates browser instantly
- **No restart needed** for most changes

### Stopping Services

- **Backend**: Press `Ctrl+C` in backend terminal
- **Frontend**: Press `Ctrl+C` in frontend terminal

---

## Production Deployment

See [`render.yaml`](render.yaml) for Render.com deployment configuration.

Quick deploy:
1. Push to GitHub
2. Connect repo to Render.com
3. Render auto-detects `render.yaml`
4. Set environment variables in Render dashboard
5. Deploy!

---

## File Structure

```
alsign/
├── backend/               # FastAPI backend
│   ├── src/
│   │   ├── main.py       # App entry point
│   │   ├── config.py     # Environment config
│   │   ├── routers/      # API endpoints
│   │   ├── services/     # Business logic
│   │   └── database/     # DB connection & queries
│   ├── scripts/
│   │   ├── setup_supabase.sql          # Database schema
│   │   └── test_supabase_connection.py # Connection test
│   ├── .env              # ✅ Pre-configured
│   └── requirements.txt
│
├── frontend/              # React frontend
│   ├── src/
│   │   ├── main.jsx      # App entry point
│   │   ├── components/   # Reusable components
│   │   ├── pages/        # Route pages
│   │   ├── services/     # API client
│   │   └── styles/       # CSS (design system)
│   ├── .env              # ✅ Pre-configured
│   └── package.json
│
├── README.md             # Project overview
├── QUICKSTART.md         # ⭐ This file
├── SUPABASE_SETUP.md     # Detailed database setup
└── render.yaml           # Deployment config
```

---

## Helpful Resources

- **Backend README**: [`backend/README.md`](backend/README.md) *(to be created)*
- **Frontend README**: [`frontend/README.md`](frontend/README.md) ✅
- **Supabase Setup**: [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md) ✅
- **API Docs**: http://localhost:8000/docs (when backend running)
- **Design System**: `prompt/2_designSystem.ini`

---

## Getting Help

### Check Logs

**Backend logs**: Visible in terminal where uvicorn is running

**Frontend logs**: Open browser DevTools (F12) → Console tab

### Verify Services

```bash
# Test backend health
curl http://localhost:8000/health

# Check if frontend is running
curl http://localhost:3000
```

### Common Commands

```bash
# Backend
cd backend
pip install -r requirements.txt          # Install deps
python scripts/test_supabase_connection.py  # Test DB
uvicorn src.main:app --reload            # Start server

# Frontend
cd frontend
npm install                              # Install deps
npm run dev                              # Start dev server
npm run build                            # Build for production
```

---

## Success Checklist

Before considering setup complete, verify:

- [ ] Supabase project is active
- [ ] 11 database tables created
- [ ] Backend connection test passes
- [ ] Backend health endpoint returns `"status": "healthy"`
- [ ] Frontend loads at http://localhost:3000
- [ ] All 4 frontend routes load without errors
- [ ] API request from frontend works (test with /health)
- [ ] No CORS errors in browser console

---

## What's Next?

1. **Populate data** using `/sourceData` endpoint
2. **Explore API** via interactive docs
3. **Configure rate limits** in Control page
4. **Create condition groups** for filtering
5. **View metrics** in Dashboard
6. **Deploy to production** using render.yaml

Congratulations! Your AlSign system is ready! 🎉
