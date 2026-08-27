"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { authApi, User, UserLoginPayload } from "../../lib/api/auth";
import { getToken, clearToken } from "../../lib/security/token";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (payload: UserLoginPayload) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refreshProfile = async () => {
    try {
      const profile = await authApi.getProfile();
      setUser(profile);
      setError(null);
    } catch (err: any) {
      setUser(null);
      // If unauthorized, ensure storage token is scrubbed
      if (err.status === 401) {
        clearToken();
      }
      throw err;
    }
  };

  // Hydrate session profile on page mount
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }

    refreshProfile()
      .catch(() => {})
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const login = async (payload: UserLoginPayload) => {
    setLoading(true);
    setError(null);
    try {
      await authApi.login(payload);
      await refreshProfile();
    } catch (err: any) {
      setError(err.message || "Authentication failed");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    authApi.logout();
    setUser(null);
    setError(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
