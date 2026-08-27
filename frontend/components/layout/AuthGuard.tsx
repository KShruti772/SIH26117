"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../providers/AuthProvider";
import { ShieldAlert } from "lucide-react";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [user, loading, router]);

  // Render high-fidelity security loader
  if (loading) {
    return (
      <div className="h-screen w-screen bg-[#0a0f1d] flex flex-col items-center justify-center space-y-4">
        <div className="relative flex items-center justify-center">
          {/* Pulsing glow ring */}
          <div className="absolute h-12 w-12 rounded-full border border-blue-500/30 animate-ping opacity-70" />
          <div className="h-10 w-10 rounded bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
            <ShieldAlert className="h-5 w-5 animate-pulse" />
          </div>
        </div>
        <span className="text-xs uppercase tracking-[0.25em] text-slate-400 font-mono">
          Verifying Sovereign Token...
        </span>
      </div>
    );
  }

  // If loading is done but no user, wait for the redirect
  if (!user) {
    return null;
  }

  return <>{children}</>;
}
