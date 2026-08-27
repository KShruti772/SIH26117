"use client";

import React, { useEffect, useState } from "react";
import { Shield, ShieldAlert, ShieldCheck, LogOut, User as UserIcon } from "lucide-react";
import { authApi, User } from "../../lib/api/auth";

export default function Header() {
  const [user, setUser] = useState<User | null>(null);
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    // 1. Fetch backend health state
    fetch("/health")
      .then((res) => res.json())
      .then((data) => setBackendHealthy(data.status === "ok"))
      .catch(() => setBackendHealthy(false));

    // 2. Fetch current profile if authenticated
    authApi.getProfile()
      .then((profile) => setUser(profile))
      .catch(() => setUser(null));
  }, []);

  const handleLogout = () => {
    authApi.logout();
    window.location.reload();
  };

  return (
    <header className="h-16 border-b border-white/5 bg-[#0e1626]/80 backdrop-blur-md px-6 flex items-center justify-between shrink-0">
      {/* Security Brand Title */}
      <div className="flex items-center space-x-3">
        <span className="text-xs uppercase tracking-[0.2em] text-blue-400 font-semibold font-mono">
          Sovereign Node / Active
        </span>
      </div>

      {/* Info Group & Profile Actions */}
      <div className="flex items-center space-x-6">
        {/* Backend health status badge */}
        <div className="flex items-center space-x-2">
          {backendHealthy === null ? (
            <span className="h-2 w-2 rounded-full bg-yellow-500 animate-pulse" />
          ) : backendHealthy ? (
            <div className="flex items-center space-x-1.5 text-xs text-emerald-400 font-mono">
              <ShieldCheck className="h-4 w-4" />
              <span>Core Online</span>
            </div>
          ) : (
            <div className="flex items-center space-x-1.5 text-xs text-rose-500 font-mono">
              <ShieldAlert className="h-4 w-4" />
              <span>Core Offline</span>
            </div>
          )}
        </div>

        {/* User Card */}
        {user ? (
          <div className="flex items-center space-x-4 border-l border-white/5 pl-6">
            <div className="flex flex-col text-right">
              <span className="text-sm font-medium text-slate-200">{user.username}</span>
              <span className="text-[10px] font-mono text-blue-400 uppercase tracking-wider">{user.role}</span>
            </div>
            <div className="h-8 w-8 rounded bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
              <UserIcon className="h-4 w-4" />
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-rose-400 transition-colors p-1.5 hover:bg-rose-500/10 rounded cursor-pointer"
              title="Logout"
              aria-label="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex items-center space-x-2 border-l border-white/5 pl-6">
            <span className="text-xs text-slate-400 font-mono">CONFIDENTIAL ACCESS</span>
          </div>
        )}
      </div>
    </header>
  );
}
