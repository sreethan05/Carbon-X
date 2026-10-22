import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { getMe } from '../services/api';

const AuthContext = createContext(null);

function safeGetStorage(key, fallback = null) {
  try {
    const val = localStorage.getItem(key);
    if (val === null || val === undefined || val === 'undefined') return fallback;
    return val;
  } catch {
    return fallback;
  }
}

function safeGetJson(key, fallback = null) {
  try {
    const val = safeGetStorage(key);
    if (!val || val === 'null') return fallback;
    return JSON.parse(val);
  } catch {
    return fallback;
  }
}

function safeSetStorage(key, value) {
  try {
    if (value === null || value === undefined) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
    }
  } catch (e) {
    console.warn(`Failed to persist ${key} to localStorage:`, e);
  }
}

function safeRemoveStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch (e) {
    console.warn(`Failed to remove ${key} from localStorage:`, e);
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => safeGetJson('carbonx_user', null));
  const [token, setToken] = useState(() => {
    const t = safeGetStorage('carbonx_token');
    return (t && t !== 'null' && t !== 'undefined' && t.trim() !== '') ? t.trim() : null;
  });
  const [farms, setFarms] = useState(() => safeGetJson('carbonx_farms', []));
  const [kyc, setKyc] = useState(() => safeGetJson('carbonx_kyc', null));
  // Do not render protected routes as logged-out while a persisted session is
  // being validated; otherwise a page refresh can incorrectly bounce users.
  const [loading, setLoading] = useState(() => Boolean(safeGetStorage('carbonx_token')));

  // Track mounted state to prevent state updates after unmount
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setFarms([]);
    setKyc(null);
    safeRemoveStorage('carbonx_token');
    safeRemoveStorage('carbonx_user');
    safeRemoveStorage('carbonx_farms');
    safeRemoveStorage('carbonx_kyc');
  }, []);

  const syncLanguage = useCallback((lang) => {
    if (!lang) return;
    safeSetStorage('carbonx_lang', lang);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('carbonx:language', { detail: { lang } }));
    }
  }, []);

  const refreshUser = useCallback(async (explicitToken) => {
    const activeToken = explicitToken || safeGetStorage('carbonx_token');
    if (!activeToken || activeToken === 'null' || activeToken === 'undefined') {
      return;
    }

    try {
      if (isMountedRef.current) setLoading(true);
      const data = await getMe();

      // Guard: Discard if unmounted or if the session was cleared/changed while awaiting
      if (!isMountedRef.current) return;
      const currentToken = safeGetStorage('carbonx_token');
      if (!currentToken || currentToken !== activeToken) return;

      if (data.success) {
        setUser(data.user);
        setFarms(data.farms || []);
        setKyc(data.kyc || null);
        safeSetStorage('carbonx_user', data.user);
        safeSetStorage('carbonx_farms', data.farms || []);
        safeSetStorage('carbonx_kyc', data.kyc || null);
        if (data.user?.preferred_language) {
          syncLanguage(data.user.preferred_language);
        }
      } else if (data.code === 'UNAUTHORIZED' || data.status === 401) {
        // Stale/expired token — drop the session instead of pretending to be signed in
        logout();
      }
    } catch (e) {
      console.warn('Could not refresh user:', e);
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, [logout, syncLanguage]);

  useEffect(() => {
    if (token) {
      refreshUser(token);
    }
  }, [token, refreshUser]);

  // Global listener for 401 UNAUTHORIZED notifications dispatched by api.js
  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
    };
    window.addEventListener('carbonx:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('carbonx:unauthorized', handleUnauthorized);
    };
  }, [logout]);

  // Cross-tab synchronization via localStorage storage event
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === 'carbonx_token') {
        const newToken = e.newValue;
        if (!newToken || newToken === 'null') {
          logout();
        } else if (newToken !== token) {
          setToken(newToken);
          const newUser = safeGetJson('carbonx_user', null);
          if (newUser) setUser(newUser);
        }
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [token, logout]);

  const login = useCallback(async (tokenValue, userData) => {
    const cleanToken = typeof tokenValue === 'string' ? tokenValue.trim() : tokenValue;
    setToken(cleanToken);
    setUser(userData);
    safeSetStorage('carbonx_token', cleanToken);
    safeSetStorage('carbonx_user', userData);
    if (userData?.preferred_language) {
      syncLanguage(userData.preferred_language);
    }
    // Perform background refresh to fetch latest farms & kyc
    await refreshUser(cleanToken);
  }, [refreshUser, syncLanguage]);

  const addFarm = useCallback((farm) => {
    if (!farm) return;
    setFarms((prevFarms) => {
      const currentList = Array.isArray(prevFarms) ? prevFarms : [];
      const updated = [farm, ...currentList.filter((f) => f.id !== farm.id)];
      safeSetStorage('carbonx_farms', updated);
      return updated;
    });
  }, []);

  const setUserProfile = useCallback((profile) => {
    if (!profile) return;
    setUser(profile);
    safeSetStorage('carbonx_user', profile);
    if (profile.preferred_language) {
      syncLanguage(profile.preferred_language);
    }
  }, [syncLanguage]);

  const role = user?.role || 'farmer';
  const isAuthenticated = !!token && !!user;

  const contextValue = useMemo(() => ({
    user,
    token,
    farms,
    kyc,
    role,
    isAuthenticated,
    loading,
    login,
    logout,
    addFarm,
    refreshUser,
    setUserProfile,
  }), [
    user,
    token,
    farms,
    kyc,
    role,
    isAuthenticated,
    loading,
    login,
    logout,
    addFarm,
    refreshUser,
    setUserProfile,
  ]);

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    return {
      user: null,
      token: null,
      farms: [],
      kyc: null,
      role: 'farmer',
      isAuthenticated: false,
      loading: false,
      login: async () => {},
      logout: () => {},
      addFarm: () => {},
      refreshUser: async () => {},
      setUserProfile: () => {},
    };
  }
  return context;
}
