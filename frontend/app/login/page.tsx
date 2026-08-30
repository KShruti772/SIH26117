"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../components/providers/AuthProvider";
import { ShieldCheck, Eye, EyeOff, Loader2, AlertCircle, Lock } from "lucide-react";

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  // Custom user-facing error state
  const [clientError, setClientError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [expiredNotice, setExpiredNotice] = useState<boolean>(false);

  // Check URL query parameters for session expiration notice
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("expired") === "true") {
        setExpiredNotice(true);
      }
    }
  }, []);

  // Redirect if already authenticated
  useEffect(() => {
    if (user) {
      router.replace("/");
    }
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setClientError(null);
    setAuthError(null);
    setExpiredNotice(false);

    // Client-side input validation
    if (!username.trim()) {
      setClientError("Please enter your username.");
      return;
    }
    if (!password) {
      setClientError("Please enter your password.");
      return;
    }

    setLoading(true);
    try {
      await login({ username: username.trim(), password });
      router.push("/");
    } catch (err: any) {
      const msg = err.message || "";
      if (msg.includes("Failed to fetch") || msg.includes("Network error") || err.status === 0) {
        setAuthError("Unable to connect to the AEGIS backend. Please ensure the local backend service is running.");
      } else if (msg.includes("401") || msg.includes("credentials") || msg.includes("Unauthorized") || msg.includes("password") || msg.includes("Invalid")) {
        setAuthError("Invalid username or password.");
      } else {
        setAuthError("Something went wrong while signing you in. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen bg-[#070b14] text-slate-100 flex flex-col justify-between p-6 md:p-10 font-sans selection:bg-blue-500/30 relative overflow-hidden">
      {/* Subtle ambient lighting */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[500px] w-[500px] rounded-full bg-blue-600/10 blur-[150px] pointer-events-none" />
      <div className="absolute bottom-10 right-10 h-72 w-72 rounded-full bg-indigo-600/5 blur-[120px] pointer-events-none" />

      {/* Top Header Branding & System Badges */}
      <header className="w-full max-w-6xl mx-auto flex items-center justify-between z-10">
        <div className="flex items-center space-x-3">
          <div className="h-9 w-9 rounded-lg bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400 shadow-lg shadow-blue-500/5">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-wider text-slate-100 uppercase">AEGIS</span>
            <span className="text-[11px] text-slate-400 font-medium">Sovereign Agentic AI Workbench</span>
          </div>
        </div>

        <div className="hidden sm:flex items-center space-x-2 text-xs text-slate-400 bg-slate-900/60 border border-slate-800/80 px-3 py-1.5 rounded-full backdrop-blur-md">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-semibold text-slate-300">On-Premise Deployment</span>
          <span className="text-slate-600">•</span>
          <span>Air-Gapped</span>
        </div>
      </header>

      {/* Main Centered Login Card */}
      <main className="w-full max-w-md mx-auto my-auto z-10 py-8">
        <div className="bg-[#0d1322]/90 border border-slate-800/90 backdrop-blur-xl rounded-2xl p-8 md:p-10 shadow-2xl shadow-black/80 relative overflow-hidden transition-all">
          {/* Top subtle blue accent gradient bar */}
          <div className="h-1 w-full bg-gradient-to-r from-blue-500 via-indigo-500 to-cyan-400 absolute top-0 left-0" />

          {/* Header Block */}
          <div className="text-center mb-8">
            <div className="h-12 w-12 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center shadow-lg shadow-blue-500/5 mb-4 mx-auto">
              <Lock className="h-6 w-6" />
            </div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Sign in to AEGIS</h1>
            <p className="text-xs text-slate-400 leading-relaxed mt-2 max-w-xs mx-auto">
              Secure access to your organization&apos;s private AI workspace.
            </p>
          </div>

          {/* Session Expired Notice */}
          {expiredNotice && !clientError && !authError && (
            <div className="mb-6 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-start space-x-3 text-amber-300">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed font-medium">
                Your session has expired. Please sign in again to continue.
              </div>
            </div>
          )}

          {/* User Error Alert */}
          {(clientError || authError) && (
            <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start space-x-3 text-rose-300">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <div className="text-xs leading-relaxed font-medium">
                {clientError || authError}
              </div>
            </div>
          )}

          {/* Credentials Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Username Input */}
            <div className="space-y-1.5">
              <label htmlFor="username-input" className="text-xs font-semibold text-slate-300 block">
                Username
              </label>
              <input
                id="username-input"
                name="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                disabled={loading}
                autoComplete="username"
                required
                className="w-full px-4 py-2.5 bg-[#080d1a] border border-slate-800 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/60 transition-all disabled:opacity-50"
              />
            </div>

            {/* Password Input */}
            <div className="space-y-1.5">
              <label htmlFor="password-input" className="text-xs font-semibold text-slate-300 block">
                Password
              </label>
              <div className="relative">
                <input
                  id="password-input"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  disabled={loading}
                  autoComplete="current-password"
                  required
                  className="w-full pl-4 pr-11 py-2.5 bg-[#080d1a] border border-slate-800 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500/60 transition-all disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  disabled={loading}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition-colors p-1 cursor-pointer disabled:opacity-50 focus:outline-none"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-lg text-sm font-semibold tracking-wide shadow-lg shadow-blue-600/20 transition-all flex items-center justify-center space-x-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500/50 mt-2"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-white/80" />
                  <span>Signing in...</span>
                </>
              ) : (
                <span>Sign In</span>
              )}
            </button>
          </form>

          {/* Security & Deployment Footer Note */}
          <div className="mt-8 pt-5 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-sans">
            <span className="flex items-center space-x-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span>Local Deployment</span>
            </span>
            <span className="text-slate-400 font-medium">Privacy-First</span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="w-full max-w-6xl mx-auto text-center text-xs text-slate-400 font-sans space-y-1 z-10">
        <div>AEGIS • Sovereign AI Infrastructure</div>
        <div className="text-[11px] text-slate-400">Local deployment • Privacy-first • Enterprise security</div>
      </footer>
    </div>
  );
}
