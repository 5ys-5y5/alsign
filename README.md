# AlSign - Financial Data API System

A comprehensive JSON-only Web API for financial data collection, processing, and analysis. Built with FastAPI and React, designed for deployment on Render.com with Supabase PostgreSQL.

> **Quick Start**: Follow the complete setup guide in [`QUICKSTART.md`](QUICKSTART.md) to get the system running in 15 minutes.

## Features

### Backend API (FastAPI)
- **Data Collection** (GET /sourceData) - Fetch holiday calendars, target tickers, consensus data, and earnings from FMP APIs
- **Event Consolidation** (POST /setEventsTable) - Consolidate events from evt_* tables into txn_events
- **Event Valuation** (POST /backfillEventsTable) - Calculate quantitative/qualitative valuations and price trends
- **Analyst Performance** (POST /fillAnalyst) - Aggregate analyst performance metrics
- **Condition Groups** - Manage condition groups for data filtering
- **Dashboard Metrics** - KPIs, performance summaries, and day-offset analytics
- **Control Panel** - API configuration and data management

### Frontend UI (React + Vite)
- **Dashboard** - KPI cards, performance tables, day-offset metrics with filtering/sorting
- **Condition Groups** - UI for creating and managing condition groups
- **Requests** - Interactive forms for executing backend API requests
- **Control** - API service configuration and data catalogs
- **Design System** - Complete design token system with no external UI libraries

## Tech Stack

### Backend
- **FastAPI** - Modern async web framework
- **asyncpg** - Async PostgreSQL driver
- **Pydantic** - Data validation
- **Python 3.11+**

### Frontend
- **React 18.2** - UI framework
- **Vite 5.0** - Build tool
- **Plain CSS** - No UI component libraries (following design system spec)
- **Hash-based routing** - Client-side navigation

### Database
- **PostgreSQL** - Main database (Supabase recommended)
- Tables: config_lv0-lv3, evt_*, txn_events

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- **Supabase account** (PostgreSQL 14+ hosted) - **✅ Pre-configured**
- FMP API key (https://financialmodelingprep.com)

> **Note**: This project is pre-configured for Supabase. See [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md) for complete setup instructions.

### Backend Setup

1. **Install dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Set environment variables:**

   **✅ Already configured for Supabase!**

   The `.env` file has been pre-created with Supabase connection details.

   **Action required**: Add your FMP API key to `backend/.env`:
   ```env
   FMP_API_KEY=your_fmp_api_key_here
   ```

3. **Initialize database:**

   **Follow the Supabase setup guide**: [`SUPABASE_SETUP.md`](SUPABASE_SETUP.md)

   Quick summary:
   ```bash
   # 1. Open Supabase SQL Editor
   # 2. Copy content from backend/scripts/setup_supabase.sql
   # 3. Paste and run in SQL Editor
   # 4. Verify 11 tables created

   # Test connection
   cd backend
   python scripts/test_supabase_connection.py
   ```

4. **Run development server:**
   ```bash
   cd backend
   uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Access API:**
   - API: http://localhost:8000
   - Interactive docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/health

### Frontend Setup

**✅ Pre-configured and ready to run!**

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Environment variables:**

   The `.env` file is **already created** with default configuration.
   No changes needed for local development.

3. **Run development server:**
   ```bash
   npm run dev
   ```

4. **Access UI:**
   - Frontend: http://localhost:3000
   - All routes:
     - Control: http://localhost:3000/#/control
     - Requests: http://localhost:3000/#/requests
     - Condition Groups: http://localhost:3000/#/conditionGroup
     - Dashboard: http://localhost:3000/#/dashboard

**Complete frontend documentation**: See [`frontend/README.md`](frontend/README.md)

## Project Structure

```
alsign/
├── backend/
│   ├── src/
│   │   ├── config.py              # Application configuration
│   │   ├── main.py                # FastAPI app entry point
│   │   ├── database/
│   │   │   ├── connection.py      # Database connection pool
│   │   │   ├── schema.sql         # Database schema
│   │   │   └── queries/           # Query modules
│   │   ├── middleware/
│   │   │   ├── logging_middleware.py
│   │   │   └── error_handler.py   # Global error handling
│   │   ├── models/                # Pydantic models
│   │   ├── routers/               # API route handlers
│   │   │   ├── source_data.py     # GET /sourceData
│   │   │   ├── events.py          # POST /setEventsTable, /backfillEventsTable
│   │   │   ├── analyst.py         # POST /fillAnalyst
│   │   │   ├── condition_group.py # /conditionGroups endpoints
│   │   │   ├── dashboard.py       # /dashboard endpoints
│   │   │   └── control.py         # /control endpoints
│   │   ├── services/              # Business logic
│   │   └── utils/                 # Utilities (logging, validation)
│   ├── scripts/
│   │   └── seed_data.py           # Database seeding script
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.jsx               # React entry point
│   │   ├── components/
│   │   │   ├── AppRouter.jsx      # Hash-based router
│   │   │   ├── dashboard/         # Dashboard components
│   │   │   ├── forms/             # Form components
│   │   │   └── table/             # Table system components
│   │   ├── pages/                 # Route pages
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── ConditionGroupPage.jsx
│   │   │   ├── RequestsPage.jsx
│   │   │   └── ControlPage.jsx
│   │   ├── services/              # API services, localStorage
│   │   └── styles/                # Design system CSS
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── prompt/                        # Design specifications
├── specs/                         # Feature specifications
├── render.yaml                    # Render.com deployment config
└── README.md
```

## API Endpoints

### Data Collection
- `GET /sourceData` - Collect data from FMP APIs
  - Query params: mode, past, calc_mode

### Event Processing
- `POST /setEventsTable` - Consolidate evt_* tables
  - Query params: overwrite, dryRun, schema, table
- `POST /backfillEventsTable` - Calculate valuations
  - Query params: from, to
- `POST /fillAnalyst` - Aggregate analyst performance

### Condition Groups
- `GET /conditionGroups/columns` - Get allowed columns
- `GET /conditionGroups/values` - Get distinct values
- `GET /conditionGroups` - List condition groups
- `POST /conditionGroups` - Create condition group
- `DELETE /conditionGroups/{name}` - Delete condition group

### Dashboard
- `GET /dashboard/kpis` - Get KPI metrics
- `GET /dashboard/performanceSummary` - Get txn_events with filtering/sorting
- `GET /dashboard/dayOffsetMetrics` - Get day-offset aggregated metrics

### Control
- `GET /control/apiServices` - Get API configurations
- `PUT /control/apiServices/{service}` - Update API configuration
- `GET /control/runtime` - Get runtime information
- `GET /control/apiList` - Get API catalog
- `GET /control/metrics` - Get metric definitions
- `GET /control/metricTransforms` - Get metric transforms

### System
- `GET /health` - Health check with database status

## Deployment

### Render.com (Recommended)

1. **Connect Repository:**
   - Push code to GitHub
   - Connect repository to Render.com

2. **Deploy via Blueprint:**
   ```bash
   # Render will automatically detect render.yaml
   # Or manually create services from dashboard
   ```

3. **Set Environment Variables:**
   - In Render dashboard, set:
     - `FMP_API_KEY`
     - Other API keys as needed

4. **Initialize Database:**
   - After first deploy, run schema setup via Render Shell
   - Run seed script if desired

### Manual Deployment

See `render.yaml` for detailed configuration.

## Development Workflow

### Running Tests
```bash
# Backend tests (if implemented)
cd backend
pytest

# Frontend tests (if implemented)
cd frontend
npm test
```

### Code Quality
```bash
# Backend linting
cd backend
flake8 src/
black src/

# Frontend linting
cd frontend
npm run lint
```

### Database Migrations
```bash
# Run SQL migrations manually or use migration tool
psql $DATABASE_URL -f backend/migrations/001_add_new_column.sql
```

## Design System

The frontend follows a strict design system specification (see `prompt/2_designSystem.ini`):

### Key Principles
- **No UI component libraries** (shadcn/ui, MUI, Ant, Chakra, Mantine)
- **No icon libraries** (lucide-react, heroicons) - uses inline SVG
- **Exact dimensions** - Button heights: 32px (sm), 40px (md)
- **8px spacing grid** - Only 8/12/16/24/32px spacing values
- **Font weights** - Only 400/500/600
- **Z-index layering** - Strict z-index values (0/10/20/21/30/100/200)

### Design Tokens
Located in `frontend/src/styles/design-tokens.css`:
- Colors, spacing, typography, dimensions
- All components use CSS variables

## Database Schema

### Config Tables
- `config_lv0_policy` - Policy definitions
- `config_lv1_api_service` - API service configurations
- `config_lv1_api_list` - API catalog
- `config_lv2_metric` - Metric definitions
- `config_lv2_metric_transform` - Metric transformations
- `config_lv3_market_holidays` - Market holiday calendar
- `config_lv3_targets` - Target ticker list
- `config_lv3_analyst` - Analyst performance data

### Event Tables
- `evt_consensus` - Consensus data (Phase 1 & 2)
- `evt_earning` - Earnings data
- `txn_events` - Consolidated events with valuations

## Environment Variables

### Backend
- `DATABASE_URL` - PostgreSQL connection string
- `FMP_API_KEY` - Financial Modeling Prep API key
- `LOG_LEVEL` - Logging level (DEBUG/INFO/WARNING/ERROR)
- `CORS_ORIGINS` - Allowed CORS origins (comma-separated)

### Frontend
- `VITE_API_BASE_URL` - Backend API base URL

## Troubleshooting

### Database Connection Issues
```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check pool status
curl http://localhost:8000/health
```

### CORS Errors
- Update `CORS_ORIGINS` in backend .env
- Ensure frontend URL is included

### API Key Issues
- Verify FMP_API_KEY is set correctly
- Check API quota limits
- Review logs for specific error messages

### Frontend Build Issues
```bash
# Clear node modules and rebuild
rm -rf node_modules package-lock.json
npm install
npm run build
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is private and proprietary.

## Support

For issues and questions:
- Check `/health` endpoint for system status
- Review logs in `backend/logs/` or Render dashboard
- Consult API documentation at `/docs`

## Acknowledgments

- FastAPI framework
- React community
- Financial Modeling Prep API
- Design system specification authors
