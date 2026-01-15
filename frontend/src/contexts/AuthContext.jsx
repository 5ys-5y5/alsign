import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { supabase } from '../services/supabaseClient';

const AuthContext = createContext(null);

function parseSubscription(metadata) {
  const status = metadata?.subscription_status || 'inactive';
  const expiresAtRaw = metadata?.subscription_expires_at || null;
  const expiresAt = expiresAtRaw ? new Date(expiresAtRaw) : null;

  let isSubscriber = status === 'active';
  if (isSubscriber && expiresAt && !Number.isNaN(expiresAt.getTime())) {
    isSubscriber = expiresAt.getTime() > Date.now();
  }

  return { status, expiresAtRaw, isSubscriber };
}

function parseRole(metadata, fallbackRole) {
  return metadata?.role || fallbackRole || 'user';
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const loadSession = async () => {
      const { data } = await supabase.auth.getSession();
      if (!mounted) return;
      setSession(data?.session || null);
      setLoading(false);
    };

    loadSession();

    const { data: authListener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });

    return () => {
      mounted = false;
      authListener?.subscription?.unsubscribe();
    };
  }, []);

  const loadProfile = useCallback(async (userId) => {
    if (!userId) {
      setProfile(null);
      setProfileLoading(false);
      return;
    }

    setProfileLoading(true);
    const { data, error } = await supabase
      .from('user_profiles')
      .select('is_admin,is_paying,subscription_expires_at')
      .eq('user_id', userId)
      .maybeSingle();

    if (error) {
      setProfile(null);
    } else {
      setProfile(data || null);
    }
    setProfileLoading(false);
  }, []);
  const refreshProfile = useCallback(async () => {
    await loadProfile(session?.user?.id);
  }, [loadProfile, session?.user?.id]);

  useEffect(() => {
    let mounted = true;
    const userId = session?.user?.id;

    const load = async () => {
      if (!mounted) return;
      await loadProfile(userId);
    };

    load();

    return () => {
      mounted = false;
    };
  }, [session?.user?.id, loadProfile]);

  const authState = useMemo(() => {
    const user = session?.user || null;
    const appMetadata = user?.app_metadata || {};
    const userMetadata = user?.user_metadata || {};
    const mergedMetadata = { ...appMetadata, ...userMetadata };

    const role = parseRole(mergedMetadata, appMetadata?.role);
    const { status, expiresAtRaw, isSubscriber } = parseSubscription(mergedMetadata);

    const subscriptionExpiresAt = profile?.subscription_expires_at
      ? new Date(profile.subscription_expires_at)
      : null;
    const isProfilePaying = Boolean(profile?.is_paying)
      && (!subscriptionExpiresAt || subscriptionExpiresAt > new Date());
    const isAdmin = Boolean(profile?.is_admin) || role === 'admin';
    const isPaying = isProfilePaying || isSubscriber;

    return {
      loading: loading || profileLoading,
      session,
      user,
      role,
      subscriptionStatus: status,
      subscriptionExpiresAt: expiresAtRaw,
      isAdmin,
      isPaying,
      profile,
      subscriptionExpiresAt: subscriptionExpiresAt ? subscriptionExpiresAt.toISOString() : null,
      refreshProfile,
      isSubscriber,
      isAuthenticated: Boolean(user),
    };
  }, [session, loading, profile, profileLoading, refreshProfile]);

  return (
    <AuthContext.Provider value={authState}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
