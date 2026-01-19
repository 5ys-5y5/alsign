/**
 * AppRouter Component
 *
 * Simple hash-based router for navigation between routes.
 * Based on alsign/prompt/2_designSystem.ini route contract.
 */

import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import ControlPage from '../pages/ControlPage';
import RequestsPage from '../pages/RequestsPage';
import SetRequestsPage from '../pages/SetRequestsPage';
import ConditionGroupPage from '../pages/ConditionGroupPage';
import DashboardPage from '../pages/DashboardPage';
import TradesPage from '../pages/TradesPage';
import HistoryPage from '../pages/HistoryPage';
import EventsHistoryPage from '../pages/EventsHistoryPage';
import ProfilePage from '../pages/ProfilePage';
import AuthModal from './AuthModal';
import BottomPanel from './BottomPanel';
import { LogProvider, useLog } from '../contexts/LogContext';
import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { supabase } from '../services/supabaseClient';

/**
 * ContentWrapper - Common layout wrapper that adjusts for BottomPanel position.
 * Applies consistent layout across all pages.
 */
function usePanelWrapperStyle() {
  const { panelOpen, panelPosition, panelSize } = useLog();
  const panelWidth = panelOpen ? panelSize : 48;

  if (panelPosition === 'right') {
    return {
      paddingRight: `${panelWidth}px`,
      transition: 'padding 0.1s ease-out',
      minHeight: '100vh',
    };
  }

  return {
    paddingBottom: panelOpen ? `${panelSize + 20}px` : '80px',
    transition: 'padding 0.1s ease-out',
  };
}

function usePanelOffsetStyle() {
  const { panelOpen, panelPosition, panelSize } = useLog();
  const panelWidth = panelOpen ? panelSize : 48;

  if (panelPosition === 'right') {
    return {
      paddingRight: `${panelWidth}px`,
      transition: 'padding 0.1s ease-out',
    };
  }

  return {
    transition: 'padding 0.1s ease-out',
  };
}

function ContentWrapper({ children }) {
  const wrapperStyle = usePanelWrapperStyle();
  const getMainContentStyle = () => {
    return {
      padding: 'var(--space-4)',
      width: '98%',
      maxWidth: '1400px',
      margin: '0 auto',
    };
  };

  return (
    <div style={wrapperStyle}>
      <div style={getMainContentStyle()}>{children}</div>
    </div>
  );
}

function PanelAwareShell({ children }) {
  const wrapperStyle = usePanelOffsetStyle();
  return <div style={wrapperStyle}>{children}</div>;
}

/**
 * Route definitions following the design system contract.
 */
const ROUTES = [
  { id: 'control', label: 'control', path: '#/control', component: ControlPage, adminOnly: true },
  { id: 'requests', label: 'requests', path: '#/requests', component: RequestsPage, adminOnly: true },
  { id: 'setRequests', label: 'setRequests', path: '#/setRequests', component: SetRequestsPage, adminOnly: true },
  { id: 'conditionGroup', label: 'conditionGroup', path: '#/conditionGroup', component: ConditionGroupPage, adminOnly: true },
  { id: 'dashboard', label: 'dashboard', path: '#/dashboard', component: DashboardPage, adminOnly: true },
  { id: 'history', label: 'history', path: '#/history', component: HistoryPage, adminOnly: true },
  { id: 'events', label: 'events', path: '#/events', component: EventsHistoryPage, adminOnly: true },
  { id: 'trades', label: 'trades', path: '#/trades', component: TradesPage },
  { id: 'profile', label: 'profile', path: '#/profile', component: ProfilePage, hideInNav: true },
];

/**
 * Navigation component.
 */
function Navigation({ currentRoute, onNavigate, onOpenAuth, navRef, panelOffsetRight }) {
  const { isAdmin, isAuthenticated } = useAuth();
  const visibleRoutes = ROUTES.filter((route) => !route.hideInNav && (!route.adminOnly || isAdmin));

  return (
    <nav
      ref={navRef}
      style={{
        backgroundColor: 'white',
        borderBottom: '1px solid var(--border)',
        padding: 'var(--space-3) 0',
        position: 'fixed',
        top: 0,
        left: 0,
        right: panelOffsetRight ? `${panelOffsetRight}px` : 0,
        zIndex: 'var(--z-topbar)',
      }}
    >
      <div style={{
        width: '98%',
        maxWidth: '1400px',
        margin: '0 auto',
        padding: 'var(--space-4)',
        display: 'flex',
        gap: 'var(--space-3)',
        alignItems: 'center'
      }}>
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
        {visibleRoutes.map((route) => {
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
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
          {isAuthenticated ? (
            <>
              <button
                type="button"
                onClick={() => onNavigate('profile')}
                aria-label="Profile"
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  border: '1px solid var(--border)',
                  background: '#ffffff',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginRight: '8px',
                  cursor: 'pointer',
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 20c1.6-3.3 4.4-5 8-5s6.4 1.7 8 5" />
                </svg>
              </button>
              <button
                type="button"
                className="btn btn-sm btn-outline"
                onClick={async () => {
                  await supabase.auth.signOut();
                  onNavigate('trades');
                }}
                style={{
                  height: '32px',
                  padding: '0 14px',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
              >
                Logout
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => onOpenAuth()}
              style={{
                height: '32px',
                padding: '0 14px',
                display: 'inline-flex',
                alignItems: 'center',
              }}
            >
              Login
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}

/**
 * AppRouter component.
 */
export default function AppRouter() {
  const [currentRoute, setCurrentRoute] = useState('trades'); // Default route
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authNext, setAuthNext] = useState(null);

  // Handle hash changes
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      const baseHash = hash.split('?')[0];
      if (baseHash === '#/login') {
        setCurrentRoute('trades');
        setAuthModalOpen(true);
        return;
      }
      const route = ROUTES.find((r) => r.path === baseHash);
      if (route) {
        setCurrentRoute(route.id);
      } else {
        // Default to trades if no hash or invalid hash
        setCurrentRoute('trades');
        window.location.hash = '#/trades';
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
      setCurrentRoute(route.id);
      window.location.hash = route.path;
    }
  };

  // Get current component
  const currentRouteConfig = ROUTES.find((r) => r.id === currentRoute);
  const CurrentComponent = currentRouteConfig?.component || DashboardPage;
  const handleOpenAuth = (nextHash) => {
    setAuthNext(nextHash || null);
    setAuthModalOpen(true);
  };

  return (
    <AuthProvider>
      <LogProvider>
        <AppContent
          currentRoute={currentRoute}
          onNavigate={handleNavigate}
          CurrentComponent={CurrentComponent}
          onOpenAuth={handleOpenAuth}
          onCloseAuth={() => setAuthModalOpen(false)}
        />
        <AuthModal
          isOpen={authModalOpen}
          onClose={() => setAuthModalOpen(false)}
          nextHash={authNext}
        />
      </LogProvider>
    </AuthProvider>
  );
}

/**
 * AppContent - Inner component that uses LogContext.
 * Separated to allow useLog() hook usage inside LogProvider.
 */
function AppContent({ currentRoute, onNavigate, CurrentComponent, onOpenAuth }) {
  const { isAdmin, loading } = useAuth();
  const { panelOpen, panelPosition, panelSize } = useLog();
  const [navHeight, setNavHeight] = useState(0);
  const navRef = useRef(null);
  const routeConfig = ROUTES.find((route) => route.id === currentRoute);
  const isAdminOnly = routeConfig?.adminOnly;
  const panelOffsetRight = panelPosition === 'right' ? (panelOpen ? panelSize : 48) : 0;

  useEffect(() => {
    if (loading) return;
    if (isAdminOnly && !isAdmin) {
      onOpenAuth(window.location.hash || '#/dashboard');
      if (currentRoute !== 'trades') {
        onNavigate('trades');
      }
    }
  }, [isAdminOnly, isAdmin, loading, currentRoute, onNavigate, onOpenAuth]);

  useLayoutEffect(() => {
    if (loading) return undefined;
    const nav = navRef.current;
    if (!nav) return undefined;

    const measureNavHeight = () => {
      setNavHeight(nav.offsetHeight || 0);
    };

    measureNavHeight();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measureNavHeight);
      return () => window.removeEventListener('resize', measureNavHeight);
    }

    const observer = new ResizeObserver(measureNavHeight);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [loading]);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', backgroundColor: 'var(--surface)', padding: 'var(--space-4)' }}>
        Loading...
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--surface)' }}>
      <PanelAwareShell>
        <Navigation
          currentRoute={currentRoute}
          onNavigate={onNavigate}
          onOpenAuth={onOpenAuth}
          navRef={navRef}
          panelOffsetRight={panelOffsetRight}
        />
      </PanelAwareShell>
      <main style={{ paddingTop: navHeight ? `${navHeight}px` : '0px' }}>
        <ContentWrapper>
          {isAdminOnly && !isAdmin ? null : <CurrentComponent />}
        </ContentWrapper>
      </main>
      <BottomPanel />
    </div>
  );
}
