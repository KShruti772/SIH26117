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

  // Listen for global auth expiration event dispatched by apiFetch
  useEffect(() => {
    const handleExpired = () => {
      setUser(null);
      setError(null);
      setLoading(false);
    };

    if (typeof window !== "undefined") {
      window.addEventListener("aegis:auth_expired", handleExpired);
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("aegis:auth_expired", handleExpired);
      }
    };
  }, []);

  // Hydrate session profile on page mount
  useEffect(() => {
    console.log("[AEGIS AUTH] App initialization started");
    const token = getToken();
    if (!token) {
      console.log("[AEGIS AUTH] No active token found in storage. Initialization completed.");
      setLoading(false);
      return;
    }

    console.log("[AEGIS AUTH] Token found. Restoring active profile...");

    // Fail-safe max 4-second timeout to prevent infinite loading screens
    const safetyTimeout = setTimeout(() => {
      console.warn("[AEGIS AUTH] Safety timeout reached during auth hydration. Unblocking UI.");
      setLoading(false);
    }, 4000);

    refreshProfile()
      .then(() => {
        console.log("[AEGIS AUTH] Session profile restored successfully.");
      })
      .catch((err) => {
        console.warn("[AEGIS AUTH] Session profile restoration failed:", err?.message || err);
        setUser(null);
        if (err?.status === 401 || err?.status === 403) {
          clearToken();
        }
      })
      .finally(() => {
        clearTimeout(safetyTimeout);
        console.log("[AEGIS AUTH] Auth initialization completed.");
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
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
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
