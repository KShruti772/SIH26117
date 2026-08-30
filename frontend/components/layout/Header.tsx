"use client";

import React, { useEffect, useState } from "react";
import { Menu, Shield, LogOut } from "lucide-react";
import { useAuth } from "../providers/AuthProvider";
import { env } from "../../lib/config/env";

export type TabId = 
  | "dashboard"
  | "chat"
  | "rag"
  | "documents"
  | "models"
  | "sandbox"
  | "audit"
  | "access"
  | "settings";

interface HeaderProps {
  activeTab: TabId;
  currentModelName?: string;
  documentCount?: number;
  onMenuToggle?: () => void;
}

const TAB_BREADCRUMBS: Record<TabId, { category: string; label: string }> = {
  dashboard: { category: "WORKSPACE", label: "DASHBOARD" },
  chat: { category: "WORKSPACE", label: "AI ASSISTANT" },
  rag: { category: "KNOWLEDGE", label: "KNOWLEDGE BASE" },
  documents: { category: "KNOWLEDGE", label: "DOCUMENTS" },
  models: { category: "AI RUNTIME", label: "MODELS" },
  sandbox: { category: "AI RUNTIME", label: "SANDBOX" },
  audit: { category: "SECURITY", label: "AUDIT LEDGER" },
  access: { category: "SECURITY", label: "USER MANAGEMENT" },
  settings: { category: "SYSTEM", label: "SETTINGS" }
};

export default function Header({ 
  activeTab, 
  currentModelName, 
  onMenuToggle 
}: HeaderProps) {
  const { user, logout } = useAuth();
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${env.apiUrl}/health`)
      .then((res) => res.json())
      .then((data) => setBackendHealthy(data.status === "ok"))
      .catch(() => setBackendHealthy(false));
  }, []);

  const breadcrumb = TAB_BREADCRUMBS[activeTab] || { category: "WORKSPACE", label: "DASHBOARD" };

  return (
    <header className="h-16 lg:h-18 border-b border-slate-800/80 bg-[#070b14]/90 backdrop-blur-xl px-4 sm:px-6 lg:px-8 flex items-center justify-between shrink-0 font-sans select-none z-10 shadow-md">
      {/* Left: Mobile menu toggle + AEGIS / CATEGORY / PAGE breadcrumb */}
      <div className="flex items-center space-x-3 sm:space-x-4">
        {onMenuToggle && (
          <button
            onClick={onMenuToggle}
            className="md:hidden p-2 text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 rounded-xl cursor-pointer transition-colors"
            aria-label="Toggle Navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
        
        <div className="flex items-center space-x-2 text-xs sm:text-sm font-sans font-bold">
          <div className="flex items-center space-x-1.5">
            <Shield className="h-4 w-4 text-blue-400 shrink-0" />
            <span className="text-slate-100 uppercase tracking-wide">AEGIS</span>
          </div>
          <span className="text-slate-600 font-normal">/</span>
          <span className="text-slate-400 uppercase tracking-wide font-semibold hidden sm:inline">
            {breadcrumb.category}
          </span>
          <span className="text-slate-600 font-normal hidden sm:inline">/</span>
          <span className="text-blue-400 tracking-wide uppercase font-extrabold">
            {breadcrumb.label}
          </span>
        </div>
      </div>

      {/* Center/Right: Clean System Status Indicators */}
      <div className="flex items-center space-x-3 sm:space-x-4 text-xs font-sans">
        <div className="hidden lg:flex items-center space-x-2">
          <div className="px-3 py-1.5 bg-[#090e1a] border border-slate-800/80 rounded-xl flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-emerald-400 font-bold text-xs font-mono uppercase">NODE ONLINE</span>
          </div>

          <div className="px-3 py-1.5 bg-[#090e1a] border border-slate-800/80 rounded-xl flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-blue-400" />
            <span className="text-blue-400 font-bold text-xs font-mono uppercase">INFERENCE LOCAL</span>
          </div>

          <div className="px-3 py-1.5 bg-[#090e1a] border border-slate-800/80 rounded-xl flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-indigo-400" />
            <span className="text-indigo-300 font-bold text-xs font-mono uppercase">AIR-GAPPED</span>
          </div>

          <div className="px-3 py-1.5 bg-[#090e1a] border border-slate-800/80 rounded-xl flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-slate-500" />
            <span className="text-slate-400 font-bold text-xs font-mono uppercase">CLOUD DISABLED</span>
          </div>
        </div>

        {/* User Identity & Logout */}
        {user && (
          <div className="flex items-center space-x-3 pl-2 sm:pl-4 border-l border-slate-800/80">
            <div className="flex items-center space-x-2.5">
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-600/30 to-indigo-600/30 border border-blue-500/40 flex items-center justify-center text-blue-300 font-bold text-xs shrink-0 shadow-sm">
                {(user.username || "AG").slice(0, 2).toUpperCase()}
              </div>
              <div className="hidden sm:flex flex-col">
                <span className="text-xs font-bold text-slate-100 truncate max-w-[120px]">
                  {user.username}
                </span>
                <span className={`inline-block text-[9px] font-extrabold uppercase px-1.5 py-0.2 rounded w-fit ${
                  user.role === "admin" 
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" 
                    : "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                }`}>
                  {user.role}
                </span>
              </div>
            </div>

            <button
              onClick={logout}
              className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-xl transition-all cursor-pointer"
              title="Sign out of AEGIS Workbench"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
