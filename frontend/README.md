# AlSign Frontend

React-based frontend for the AlSign Financial Data API system.

## Tech Stack

- **React 18.2** - UI framework
- **Vite 5.0** - Build tool and dev server
- **Plain CSS** - No UI component libraries (following design system spec)
- **Hash-based routing** - Client-side navigation without external router

## Features

### Pages
- **Dashboard** - KPI cards, performance tables, day-offset metrics with filtering/sorting
- **Condition Groups** - UI for creating and managing condition groups
- **Requests** - Interactive forms for executing backend API requests
- **Control** - API service configuration and data catalogs

### Components
- **Table System** - Sortable, filterable tables with column selection and localStorage persistence
- **KPI Cards** - Dashboard metric displays
- **Forms** - Condition group creation, API request forms
- **Filters** - Multi-select filter popovers with AND-combination logic

### Design System
- **No UI libraries** - Follows strict design system specification
- **Exact dimensions** - Button heights: 32px (sm), 40px (md)
- **8px spacing grid** - Only 8/12/16/24/32px spacing values
- **SVG icons only** - No icon libraries or Unicode glyphs
- **Design tokens** - Complete CSS variable system in `src/styles/design-tokens.css`

## Getting Started

### Prerequisites

- **Node.js 18+** (LTS version recommended)
- **Backend running** at `http://localhost:8000`

### Installation

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Configure environment:**

   The `.env` file has been pre-created with default settings:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   ```

   For production deployment, update to your backend URL:
   ```env
   VITE_API_BASE_URL=https://your-backend-url.com
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```

   The app will be available at:
   - **http://localhost:5173** (Vite default)

### Build for Production

```bash
# Create optimized production build
npm run build

# Preview production build locally
npm run preview
```

The build output will be in the `dist/` directory.

## Project Structure

```
frontend/
├── src/
│   ├── main.jsx                  # Application entry point
│   ├── components/
│   │   ├── AppRouter.jsx         # Hash-based router
│   │   ├── dashboard/            # Dashboard components
│   │   │   ├── KPICard.jsx
│   │   │   ├── PerformanceTable.jsx
│   │   │   └── DayOffsetTable.jsx
│   │   ├── forms/                # Form components
│   │   │   └── ConditionGroupForm.jsx
│   │   └── table/                # Table system components
│   │       ├── DataTable.jsx
│   │       ├── SortHeader.jsx
│   │       ├── FilterPopover.jsx
│   │       └── ColumnSelector.jsx
│   ├── pages/                    # Route pages
│   │   ├── DashboardPage.jsx
│   │   ├── ConditionGroupPage.jsx
│   │   ├── RequestsPage.jsx
│   │   └── ControlPage.jsx
│   ├── services/                 # API and utility services
│   │   ├── api.js                # Centralized API client
│   │   ├── conditionGroupService.js
│   │   └── localStorage.js
│   └── styles/                   # CSS stylesheets
│       ├── design-tokens.css     # Design system variables
│       ├── global.css            # Global styles
│       └── components.css        # Component styles
├── index.html                    # HTML entry point
├── package.json
├── vite.config.js
└── .env                          # Environment variables
```

## Available Scripts

- **`npm run dev`** - Start development server with hot reload
- **`npm run build`** - Build for production
- **`npm run preview`** - Preview production build locally
- **`npm run lint`** - Run ESLint code quality checks

## Design System Compliance

The frontend strictly adheres to the design system specification in `alsign/prompt/2_designSystem.ini`.

### Key Constraints

**MUST**:
- Use exact button dimensions (32px/40px heights)
- Follow 8px spacing grid (8/12/16/24/32px only)
- Use font weights 400/500/600 only
- Use z-index values: 0/10/20/21/30/100/200
- Use SVG assets for all icons

**MUST NOT**:
- Use UI component libraries (shadcn/ui, MUI, Ant, Chakra, Mantine)
- Use icon libraries (lucide-react, heroicons, font-awesome)
- Use Unicode glyphs for functional icons
- Deviate from spacing grid or button dimensions

### Design Tokens

All design tokens are defined in `src/styles/design-tokens.css`:

```css
/* Spacing */
--spacing-xs: 8px;
--spacing-sm: 12px;
--spacing-md: 16px;
--spacing-lg: 24px;
--spacing-xl: 32px;

/* Button heights */
--btn-height-sm: 32px;
--btn-height-md: 40px;

/* Font weights */
--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;

/* Z-index layering */
--z-base: 0;
--z-dropdown: 10;
--z-sticky: 20;
--z-fixed: 21;
--z-modal-backdrop: 30;
--z-modal: 100;
--z-popover: 200;
```

## API Integration

### Centralized API Client

All API requests use the centralized `api.js` service:

```javascript
import { get, post, put, del } from './services/api';

// GET request
const kpis = await get('/dashboard/kpis');

// POST request with query params
const result = await post('/setEventsTable', {}, { dryRun: true });

// PUT request
await put('/control/apiServices/fmp', { usagePerMin: 300 });

// DELETE request
await del('/conditionGroups/myGroup');
```

### Environment Variables

The API base URL is configured via `VITE_API_BASE_URL`:

```javascript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
```

Update `.env` to change the backend URL.

## Routing

The app uses hash-based routing (no external router library):

```javascript
// Route configuration in AppRouter.jsx
const ROUTES = [
  { id: 'control', label: 'control', path: '#/control', component: ControlPage },
  { id: 'requests', label: 'requests', path: '#/requests', component: RequestsPage },
  { id: 'conditionGroup', label: 'conditionGroup', path: '#/conditionGroup', component: ConditionGroupPage },
  { id: 'dashboard', label: 'dashboard', path: '#/dashboard', component: DashboardPage },
];
```

Navigate by changing `window.location.hash`:
```javascript
window.location.hash = '#/dashboard';
```

## State Management

### LocalStorage Persistence

Table state (columns, filters, sort) is persisted to localStorage:

```javascript
import { saveTableState, loadTableState } from './services/localStorage';

// Save state
saveTableState('performanceTable', {
  visibleColumns: ['ticker', 'event_date', 'sector'],
  activeFilters: { sector: ['Technology'] },
  sortBy: 'event_date',
  sortOrder: 'desc',
});

// Load state
const state = loadTableState('performanceTable');
```

## Troubleshooting

### CORS Errors

**Error**: `Access to fetch at 'http://localhost:8000/...' from origin 'http://localhost:5173' has been blocked by CORS policy`

**Solution**: Ensure backend `CORS_ORIGINS` includes `http://localhost:5173`:

```env
# In backend/.env
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Restart backend server after changing.

### API Connection Failed

**Error**: `Failed to fetch` or `Network request failed`

**Solution**:
1. Verify backend is running at `http://localhost:8000`
2. Check backend health: http://localhost:8000/health
3. Verify `VITE_API_BASE_URL` in `.env`
4. Check browser console for detailed error

### Build Errors

**Error**: `Module not found` or import errors

**Solution**:
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf node_modules/.vite
npm run dev
```

### Hot Reload Not Working

**Solution**:
- Check file permissions
- Ensure no syntax errors in JSX
- Restart dev server: `Ctrl+C` then `npm run dev`

## Development Workflow

### Adding a New Page

1. Create page component in `src/pages/`:
   ```jsx
   // src/pages/NewPage.jsx
   export default function NewPage() {
     return <div>New Page Content</div>;
   }
   ```

2. Add route in `src/components/AppRouter.jsx`:
   ```javascript
   const ROUTES = [
     // ... existing routes
     { id: 'new', label: 'New Page', path: '#/new', component: NewPage },
   ];
   ```

3. Navigate to `#/new` in browser

### Adding a New API Endpoint

1. Add service function in relevant service file or `api.js`:
   ```javascript
   export async function getNewData() {
     return get('/newEndpoint');
   }
   ```

2. Use in component:
   ```jsx
   import { getNewData } from '../services/api';

   const data = await getNewData();
   ```

## Code Quality

### Linting

```bash
npm run lint
```

Follows ESLint with React plugins:
- `eslint-plugin-react`
- `eslint-plugin-react-hooks`

### Design System Validation

Before committing, verify:
- ✅ No hardcoded colors (use CSS variables)
- ✅ No arbitrary spacing (use 8/12/16/24/32px only)
- ✅ Button heights match spec (32px/40px)
- ✅ No icon libraries imported
- ✅ Z-index values from allowed list

## Deployment

### Render.com (Included in render.yaml)

The frontend is configured in `render.yaml`:

```yaml
- type: web
  name: alsign-frontend
  runtime: static
  buildCommand: cd frontend && npm install && npm run build
  staticPublishPath: frontend/dist
  envVars:
    - key: VITE_API_BASE_URL
      value: https://alsign-api.onrender.com
```

### Manual Deployment

1. **Build**:
   ```bash
   npm run build
   ```

2. **Deploy `dist/` folder** to static hosting:
   - Netlify
   - Vercel
   - GitHub Pages
   - S3 + CloudFront

3. **Configure environment**:
   - Set `VITE_API_BASE_URL` to production backend URL
   - Ensure backend CORS allows production frontend domain

## Performance

- **Vite HMR**: Instant hot module replacement
- **Code splitting**: Automatic chunk optimization
- **Tree shaking**: Removes unused code
- **Asset optimization**: Minified CSS/JS, optimized images

## Browser Support

- Chrome (last 2 versions)
- Firefox (last 2 versions)
- Safari (last 2 versions)
- Edge (last 2 versions)

## Contributing

1. Follow design system constraints strictly
2. No external UI libraries
3. Use CSS variables for all styling
4. Keep components self-contained
5. Document complex logic with comments

## License

This project is private and proprietary.

## Support

For frontend issues:
- Check browser console for errors
- Verify backend connectivity at `/health`
- Review Vite documentation: https://vitejs.dev/
- Check React documentation: https://react.dev/
