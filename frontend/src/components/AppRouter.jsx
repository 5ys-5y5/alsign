/**
 * AppRouter Component
 *
 * Simple hash-based router for navigation between routes.
 * Based on alsign/prompt/2_designSystem.ini route contract.
 */

import React, { useState, useEffect } from 'react';
import ControlPage from '../pages/ControlPage';
import RequestsPage from '../pages/RequestsPage';
import SetRequestsPage from '../pages/SetRequestsPage';
import ConditionGroupPage from '../pages/ConditionGroupPage';
import DashboardPage from '../pages/DashboardPage';
import BottomPanel from './BottomPanel';
import { LogProvider, useLog } from '../contexts/LogContext';

/**
 * ContentWrapper - Common layout wrapper that adjusts for BottomPanel position.
 * Applies consistent layout across all pages.
 */
function ContentWrapper({ children }) {
  const { panelOpen, panelPosition, panelSize } = useLog();

  const getWrapperStyle = () => {
    const panelWidth = panelOpen ? panelSize : 48;

    if (panelPosition === 'right') {
      return {
        marginRight: `${panelWidth}px`,
        transition: 'margin 0.1s ease-out',
        minHeight: '100vh',
      };
    } else {
      return {
        paddingBottom: panelOpen ? `${panelSize + 20}px` : '80px',
        transition: 'padding 0.1s ease-out',
      };
    }
  };

  const getMainContentStyle = () => {
    return {
      padding: 'var(--space-4)',
      width: '98%',
      maxWidth: '1400px',
      margin: '0 auto',
    };
  };

  return (
    <div style={getWrapperStyle()}>
      <div style={getMainContentStyle()}>{children}</div>
    </div>
  );
}

/**
 * Route definitions following the design system contract.
 */
const ROUTES = [
  { id: 'control', label: 'control', path: '#/control', component: ControlPage },
  { id: 'requests', label: 'requests', path: '#/requests', component: RequestsPage },
  { id: 'setRequests', label: 'setRequests', path: '#/setRequests', component: SetRequestsPage },
  { id: 'conditionGroup', label: 'conditionGroup', path: '#/conditionGroup', component: ConditionGroupPage },
  { id: 'dashboard', label: 'dashboard', path: '#/dashboard', component: DashboardPage },
];

/**
 * Navigation component.
 */
function Navigation({ currentRoute, onNavigate }) {
  return (
    <nav
      style={{
        backgroundColor: 'white',
        borderBottom: '1px solid var(--border)',
        padding: 'var(--space-3) var(--space-4)',
        position: 'sticky',
        top: 0,
        zIndex: 'var(--z-topbar)',
      }}
    >
      <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
        <div
          style={{
            fontSize: 'var(--text-lg)',
            fontWeight: 'var(--font-semibold)',
            color: 'var(--ink)',
            marginRight: 'var(--space-4)',
          }}
        >
          AlSign
        </div>
        {ROUTES.map((route) => {
          const isActive = currentRoute === route.id;
          return (
            <a
              key={route.id}
              href={route.path}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(route.id);
              }}
              style={{
                padding: 'var(--space-1) var(--space-2)',
                fontSize: 'var(--text-sm)',
                fontWeight: isActive ? 'var(--font-semibold)' : 'var(--font-normal)',
                color: isActive ? 'var(--accent-primary)' : 'var(--text)',
                textDecoration: 'none',
                borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
                transition: 'all var(--transition-base)',
              }}
            >
              {route.label}
            </a>
          );
        })}
      </div>
    </nav>
  );
}

/**
 * AppRouter component.
 */
export default function AppRouter() {
  const [currentRoute, setCurrentRoute] = useState('dashboard'); // Default route

  // Handle hash changes
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      const route = ROUTES.find((r) => r.path === hash);
      if (route) {
        setCurrentRoute(route.id);
      } else {
        // Default to dashboard if no hash or invalid hash
        setCurrentRoute('dashboard');
        window.location.hash = '#/dashboard';
      }
    };

    // Set initial route
    handleHashChange();

    // Listen for hash changes
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleNavigate = (routeId) => {
    const route = ROUTES.find((r) => r.id === routeId);
    if (route) {
      window.location.hash = route.path;
    }
  };

  // Get current component
  const currentRouteConfig = ROUTES.find((r) => r.id === currentRoute);
  const CurrentComponent = currentRouteConfig?.component || DashboardPage;

  return (
    <LogProvider>
      <AppContent
        currentRoute={currentRoute}
        onNavigate={handleNavigate}
        CurrentComponent={CurrentComponent}
      />
    </LogProvider>
  );
}

/**
 * AppContent - Inner component that uses LogContext.
 * Separated to allow useLog() hook usage inside LogProvider.
 */
function AppContent({ currentRoute, onNavigate, CurrentComponent }) {
  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--surface)' }}>
      <Navigation currentRoute={currentRoute} onNavigate={onNavigate} />
      <main>
        <ContentWrapper>
          <CurrentComponent />
        </ContentWrapper>
      </main>
      <BottomPanel />
    </div>
  );
}
