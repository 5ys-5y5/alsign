# Quickstart: FastAPI Financial Data API Backend System

**Date**: 2025-12-18
**Branch**: `001-fastapi-financial-data-api`

## Prerequisites

- Python 3.11 or higher
- Supabase account with Postgres database
- FMP (Financial Modeling Prep) API key
- Git

## Local Development Setup

### 1. Clone Repository and Checkout Branch

```bash
git clone <repository-url>
cd alsign
git checkout 001-fastapi-financial-data-api
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip
```

### 3. Install Dependencies

```bash
# Install backend dependencies
cd backend
pip install -r requirements.txt

# If using Poetry (alternative):
poetry install
```

**Core Dependencies** (add to `requirements.txt`):
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
asyncpg==0.29.0
pydantic==2.5.0
pydantic-settings==2.1.0
httpx==0.25.0
python-dateutil==2.8.2
python-multipart==0.0.6
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
respx==0.20.2
```

### 4. Configure Environment Variables

Create `.env` file in `backend/` directory:

```bash
# Database Configuration (Supabase Postgres)
DATABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/[DATABASE]?sslmode=require
DB_POOL_MIN_SIZE=10
DB_POOL_MAX_SIZE=20

# External API Configuration
FMP_API_KEY=your_fmp_api_key_here
FMP_BASE_URL=https://financialmodelingprep.com/api/v3

# API Rate Limits (calls per minute)
FMP_RATE_LIMIT=250

# Application Configuration
LOG_LEVEL=INFO
ENVIRONMENT=development

# CORS Settings (for local frontend)
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

**Security Note**: Never commit `.env` file to version control. Add to `.gitignore`.

### 5. Verify Database Schema

Ensure all tables from `alsign/prompt/1_guideline(tableSetting).ini` are created in Supabase:

```bash
# Connect to Supabase and verify tables exist:
# - config_lv0_policy
# - config_lv1_api_service
# - config_lv1_api_list
# - config_lv2_metric
# - config_lv2_metric_transform
# - config_lv3_market_holidays
# - config_lv3_targets
# - config_lv3_analyst
# - evt_consensus
# - evt_earning
# - txn_events
```

### 6. Seed Configuration Tables

```bash
# Seed policies (required for price trend calculations)
python -m scripts.seed_policies

# Seed API service configuration
python -m scripts.seed_api_config

# Seed metric definitions
python -m scripts.seed_metrics
```

**Seed Scripts Location**: `backend/scripts/`

### 7. Run Backend Server

```bash
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Verify Server**: Open http://localhost:8000/docs (FastAPI automatic OpenAPI docs)

### 8. Run Tests

```bash
# Run all tests with coverage
pytest --cov=src --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/contract/

# View coverage report
open htmlcov/index.html
```

### 9. Set Up Frontend (Optional for UI development)

```bash
cd ../frontend

# If using Vite:
npm install
npm run dev

# If using plain HTML/JS:
# Use Python http.server or any local server
python -m http.server 3000 --directory src
```

**Frontend Dev Server**: http://localhost:3000

---

## Deployment to Render.com

### 1. Prepare for Deployment

#### Create `render.yaml` in repository root:

```yaml
services:
  - type: web
    name: alsign-api
    env: python
    region: oregon
    plan: starter
    buildCommand: "pip install -r backend/requirements.txt"
    startCommand: "cd backend && uvicorn src.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: PYTHON_VERSION
        value: "3.11.5"
      - key: DATABASE_URL
        sync: false
      - key: FMP_API_KEY
        sync: false
      - key: FMP_RATE_LIMIT
        value: "250"
      - key: LOG_LEVEL
        value: "INFO"
      - key: ENVIRONMENT
        value: "production"
    healthCheckPath: /health
```

### 2. Connect Repository to Render

1. Log in to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Blueprint"
3. Connect GitHub repository
4. Render will detect `render.yaml` and create services

### 3. Configure Environment Secrets

In Render Dashboard:
1. Navigate to service → Environment
2. Add secret environment variables:
   - `DATABASE_URL`: Supabase connection string
   - `FMP_API_KEY`: Your FMP API key

### 4. Deploy

```bash
# Push to main branch (or deploy branch)
git push origin 001-fastapi-financial-data-api

# Render will automatically build and deploy
```

### 5. Verify Deployment

```bash
# Health check
curl https://alsign-api.onrender.com/health

# API docs
open https://alsign-api.onrender.com/docs
```

---

## API Usage Examples

### 1. Collect Market Holidays

```bash
curl -X GET "http://localhost:8000/sourceData?mode=holiday"
```

### 2. Collect All Source Data

```bash
curl -X GET "http://localhost:8000/sourceData"
```

### 3. Collect Consensus with Maintenance Mode

```bash
curl -X GET "http://localhost:8000/sourceData?mode=consensus&calc_mode=maintenance&calc_scope=ticker&tickers=AAPL,MSFT"
```

### 4. Consolidate Events

```bash
curl -X POST "http://localhost:8000/setEventsTable" \
  -H "Content-Type: application/json" \
  -d "{}"
```

### 5. Consolidate Events (Dry Run)

```bash
curl -X POST "http://localhost:8000/setEventsTable?dryRun=true" \
  -H "Content-Type: application/json" \
  -d "{}"
```

### 6. Calculate Valuation Metrics

```bash
curl -X POST "http://localhost:8000/backfillEventsTable" \
  -H "Content-Type: application/json" \
  -d "{}"
```

### 7. Aggregate Analyst Performance

```bash
curl -X POST "http://localhost:8000/fillAnalyst" \
  -H "Content-Type: application/json" \
  -d "{}"
```

---

## Development Workflow

### Typical Development Cycle

1. **Data Collection**: Run `GET /sourceData` to populate foundation tables
2. **Event Consolidation**: Run `POST /setEventsTable` to unify events
3. **Valuation**: Run `POST /backfillEventsTable` to calculate metrics
4. **Price Trends**: Automatically filled during valuation (or run separately)
5. **Analyst Aggregation**: Run `POST /fillAnalyst` to generate performance stats
6. **Dashboard**: View results in UI at `/dashboard` route

### Code Changes Workflow

```bash
# 1. Create feature branch
git checkout -b feature/your-feature

# 2. Make changes
# Edit files in backend/src/

# 3. Run tests
pytest tests/

# 4. Check code quality
black src/
ruff check src/

# 5. Commit and push
git add .
git commit -m "feat: your feature description"
git push origin feature/your-feature

# 6. Create pull request
```

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Fails

**Error**: `asyncpg.exceptions.InvalidPasswordError`

**Solution**:
- Verify DATABASE_URL in `.env`
- Check Supabase dashboard for connection string
- Ensure `sslmode=require` is included

#### 2. FMP API Rate Limit Exceeded

**Error**: HTTP 429 from FMP API

**Solution**:
- Check `config_lv1_api_service.usagePerMin` value
- Reduce batch sizes in service configuration
- Wait 60 seconds for rate limit window to reset

#### 3. Date Parsing Errors

**Error**: `400 Bad Request - Invalid date format`

**Solution**:
- Ensure dates are in ISO8601 format with timezone (+00:00)
- Use `YYYY-MM-DDTHH:MM:SS+00:00` for timestamps
- Use `YYYY-MM-DD` for date-only fields (treated as UTC midnight)

#### 4. Generated Column Write Errors

**Error**: `cannot insert into generated column`

**Solution**:
- Never write to: `created_at`, `updated_at`, `analyst_name_key`, `analyst_company_key`
- Remove these fields from INSERT/UPDATE statements

#### 5. Tests Fail with "Database not found"

**Solution**:
- Create separate test database: `alsign_test`
- Update `.env.test` with test database URL
- Run `pytest` with `--env-file=.env.test`

---

## Monitoring & Logs

### View Logs Locally

```bash
# Tail application logs
tail -f backend/logs/app.log

# View structured logs with filtering
grep "ERROR" backend/logs/app.log
grep "GET /sourceData" backend/logs/app.log
```

### View Logs on Render

1. Navigate to Render Dashboard
2. Select service
3. Click "Logs" tab
4. Use filter/search to find specific endpoints or errors

### Log Format

All logs follow structured format:
```
[endpoint | phase] elapsed=Xms | progress=done/total(pct%) | eta=Yms | rate=perMin/limitPerMin(usagePct%) | batch=size(mode) | ok=X fail=Y skip=Z upd=A ins=B cf=C | warn=[codes] | message
```

---

## Performance Optimization

### Database Indexing

Ensure these indexes exist for optimal query performance:

```sql
-- Consensus Phase 2 queries
CREATE INDEX idx_evt_consensus_partition ON evt_consensus(ticker, analyst_name, analyst_company, event_date DESC);

-- Event consolidation
CREATE INDEX idx_txn_events_ticker_source ON txn_events(ticker, source);

-- Trading day lookup
CREATE INDEX idx_market_holidays_exchange_date ON config_lv3_market_holidays(exchange, date);
```

### Connection Pooling

Adjust pool sizes in `.env` based on workload:
```
DB_POOL_MIN_SIZE=10   # Minimum connections
DB_POOL_MAX_SIZE=20   # Maximum connections
```

### Batch Size Tuning

Edit `backend/src/config.py`:
```python
DB_UPSERT_BATCH_SIZE = 1000  # Records per batch insert
API_BATCH_SIZE_INITIAL = 50  # Initial API batch size (dynamically adjusted)
```

---

## Next Steps

1. ✅ Complete `/speckit.plan` (this document)
2. ⏳ Run `/speckit.tasks` to generate implementation tasks
3. ⏳ Begin implementation following task order
4. ⏳ Write tests for each completed feature
5. ⏳ Deploy to Render.com staging environment
6. ⏳ Perform end-to-end testing
7. ⏳ Deploy to production

---

## Additional Resources

- **Feature Specification**: [spec.md](./spec.md)
- **Implementation Plan**: [plan.md](./plan.md)
- **Data Model**: [data-model.md](./data-model.md)
- **Research Decisions**: [research.md](./research.md)
- **API Contracts**: [contracts/](./contracts/)
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **asyncpg Documentation**: https://magicstack.github.io/asyncpg/
- **FMP API Documentation**: https://site.financialmodelingprep.com/developer/docs
