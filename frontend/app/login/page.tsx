"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../components/providers/AuthProvider";
import { Shield, Lock, Eye, EyeOff, Loader2, AlertTriangle, Key } from "lucide-react";

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  
  // Custom error states
  const [clientError, setClientError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  // Redirect if already logged in
  useEffect(() => {
    if (user) {
      router.replace("/");
    }
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setClientError(null);
    setAuthError(null);

    // 1. Client-side field validations
    if (!username.trim()) {
      setClientError("Username is required.");
      return;
    }
    if (!password) {
      setClientError("Password is required.");
      return;
    }
    if (password.length < 8) {
      setClientError("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);
    try {
      await login({ username, password });
      router.push("/");
    } catch (err: any) {
      setAuthError(err.message || "Failed to authenticate with sovereign node.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen bg-[#0a0f1d] flex items-center justify-center p-4">
      {/* Glow highlight behind container */}
      <div className="absolute h-96 w-96 rounded-full bg-blue-500/5 blur-[120px] pointer-events-none" />

      <div className="w-full max-w-[420px] bg-[#0c1220]/80 border border-white/5 backdrop-blur-md rounded-lg p-8 shadow-2xl relative">
        {/* Top brand header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="h-10 w-10 rounded bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 mb-3">
            <Shield className="h-5 w-5 animate-pulse" />
          </div>
          <h2 className="text-lg font-bold tracking-wider text-slate-100 font-mono">AEGIS // SECURE ACCESS</h2>
          <p className="text-xs text-slate-400 mt-1 font-mono">Confidential Industrial Agentic Workbench</p>
        </div>

        {/* System Alerts */}
        {(clientError || authError) && (
          <div className="mb-6 p-3 bg-rose-500/10 border border-rose-500/20 rounded flex items-start space-x-3 text-rose-400">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="flex-1 text-xs font-mono leading-relaxed">
              {clientError || authError}
            </div>
          </div>
        )}

        {/* Credentials Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Username */}
          <div className="space-y-1.5">
            <label htmlFor="username-input" className="text-[10px] font-bold text-slate-450 uppercase tracking-wider font-mono">
              Username ID
            </label>
            <div className="relative">
              <input
                id="username-input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter authorized username"
                disabled={loading}
                className="w-full px-3.5 py-2.5 bg-[#0e1626]/70 border border-white/5 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors font-mono disabled:opacity-50"
                autoComplete="username"
              />
            </div>
          </div>

          {/* Password */}
          <div className="space-y-1.5">
            <label htmlFor="password-input" className="text-[10px] font-bold text-slate-450 uppercase tracking-wider font-mono">
              Security Key
            </label>
            <div className="relative">
              <input
                id="password-input"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter credentials key"
                disabled={loading}
                className="w-full pl-3.5 pr-10 py-2.5 bg-[#0e1626]/70 border border-white/5 rounded text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500/50 transition-colors font-mono disabled:opacity-50"
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                disabled={loading}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-450 hover:text-slate-200 transition-colors p-0.5 cursor-pointer disabled:opacity-50"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Access Grant trigger */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-semibold transition-colors flex items-center justify-center space-x-2 cursor-pointer disabled:opacity-50 disabled:bg-blue-600/30"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin text-white/70" />
                <span className="font-mono text-xs uppercase tracking-wider">Verifying Claims...</span>
              </>
            ) : (
              <>
                <Key className="h-4 w-4 text-white/80" />
                <span className="font-mono text-xs uppercase tracking-wider">Request Access Grant</span>
              </>
            )}
          </button>
        </form>

        {/* Footer legalities */}
        <div className="mt-8 border-t border-white/5 pt-4 text-center">
          <span className="text-[10px] text-slate-500 font-mono block">
            This node resides on a private on-premise subnet. Access parameters are logged to the audit ledger.
          </span>
        </div>
      </div>
    </div>
  );
}
