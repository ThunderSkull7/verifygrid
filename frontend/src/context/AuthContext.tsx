import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { User } from '../types';
import { AuthContext } from './authContextDef';

export type { AuthContextType } from './authContextDef';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(api.getToken());
  const [isLoading, setIsLoading] = useState<boolean>(() => !!api.getToken());

  useEffect(() => {
    let isMounted = true;

    const initAuth = async () => {
      const storedToken = api.getToken();
      if (!storedToken) {
        if (isMounted) {
          setUser(null);
          setIsLoading(false);
        }
        return;
      }

      try {
        const userData = await api.getMe();
        if (isMounted) {
          setUser(userData);
        }
      } catch {
        api.setToken(null);
        if (isMounted) {
          setToken(null);
          setUser(null);
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    void initAuth();

    const handleUnauthorized = () => {
      if (isMounted) {
        setToken(null);
        setUser(null);
      }
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      isMounted = false;
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, []);

  const login = (newToken: string, newUser: User) => {
    api.setToken(newToken);
    setToken(newToken);
    setUser(newUser);
  };

  const logout = () => {
    api.setToken(null);
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    if (!api.getToken()) {
      setUser(null);
      return;
    }
    try {
      const userData = await api.getMe();
      setUser(userData);
    } catch {
      api.setToken(null);
      setToken(null);
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
