import React, { createContext, useContext, useState, useEffect } from 'react';
import { getMe } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('carbonx_user') || 'null'); } catch { return null; }
  });
  const [token, setToken] = useState(() => localStorage.getItem('carbonx_token') || null);
  const [farms, setFarms] = useState(() => {
    try { return JSON.parse(localStorage.getItem('carbonx_farms') || '[]'); } catch { return []; }
  });
  const [kyc, setKyc] = useState(() => {
    try { return JSON.parse(localStorage.getItem('carbonx_kyc') || 'null'); } catch { return null; }
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (token) refreshUser();
  }, [token]);

  async function refreshUser() {
    try {
      setLoading(true);
      const data = await getMe();
      if (data.success) {
        setUser(data.user);
        setFarms(data.farms || []);
        setKyc(data.kyc || null);
        localStorage.setItem('carbonx_user', JSON.stringify(data.user));
        localStorage.setItem('carbonx_farms', JSON.stringify(data.farms || []));
        localStorage.setItem('carbonx_kyc', JSON.stringify(data.kyc || null));
        if (data.user?.preferred_language) {
          localStorage.setItem('carbonx_lang', data.user.preferred_language);
        }
      }
    } catch (e) {
      console.warn('Could not refresh user:', e);
    } finally {
      setLoading(false);
    }
  }

  async function login(tokenValue, userData) {
    setToken(tokenValue);
    setUser(userData);
    localStorage.setItem('carbonx_token', tokenValue);
    localStorage.setItem('carbonx_user', JSON.stringify(userData));
    if (userData?.preferred_language) {
      localStorage.setItem('carbonx_lang', userData.preferred_language);
    }
    try {
      const data = await getMe();
      if (data.success) {
        setUser(data.user);
        setFarms(data.farms || []);
        setKyc(data.kyc || null);
        localStorage.setItem('carbonx_user', JSON.stringify(data.user));
        localStorage.setItem('carbonx_farms', JSON.stringify(data.farms || []));
        localStorage.setItem('carbonx_kyc', JSON.stringify(data.kyc || null));
        if (data.user?.preferred_language) {
          localStorage.setItem('carbonx_lang', data.user.preferred_language);
        }
      }
    } catch {
      /* keep local user */
    }
  }

  function logout() {
    setToken(null);
    setUser(null);
    setFarms([]);
    setKyc(null);
    localStorage.removeItem('carbonx_token');
    localStorage.removeItem('carbonx_user');
    localStorage.removeItem('carbonx_farms');
    localStorage.removeItem('carbonx_kyc');
  }

  function addFarm(farm) {
    const updated = [farm, ...farms.filter((f) => f.id !== farm.id)];
    setFarms(updated);
    localStorage.setItem('carbonx_farms', JSON.stringify(updated));
  }

  function setUserProfile(profile) {
    setUser(profile);
    localStorage.setItem('carbonx_user', JSON.stringify(profile));
  }

  const role = user?.role || 'farmer';
  const isAuthenticated = !!token && !!user;

  return (
    <AuthContext.Provider value={{
      user, token, farms, kyc, role, isAuthenticated, loading,
      login, logout, addFarm, refreshUser, setUserProfile,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
