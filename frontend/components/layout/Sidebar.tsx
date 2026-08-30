"use client";

import React from "react";
import { 
  ShieldCheck, 
  LayoutDashboard, 
  MessageSquareCode, 
  Database, 
  FileSpreadsheet, 
  Cpu, 
  Terminal, 
  History, 
  Users,
  CheckCircle2,
  Settings,
  Info,
  LogOut 
} from "lucide-react";
import { useAuth } from "../providers/AuthProvider";

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

interface NavigationItem {
  id: TabId;
  label: string;
  icon: React.ComponentType<any>;
  adminOnly?: boolean;
}

interface NavigationCategory {
  title: string;
  items: NavigationItem[];
}

const NAVIGATION_CATEGORIES: NavigationCategory[] = [
  {
    title: "MAIN",
    items: [
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
      { id: "chat", label: "AI Assistant", icon: MessageSquareCode },
    ]
  },
  {
    title: "KNOWLEDGE",
    items: [
      { id: "documents", label: "Documents", icon: FileSpreadsheet },
      { id: "rag", label: "Knowledge Base", icon: Database },
    ]
  },
  {
    title: "AI RUNTIME",
    items: [
      { id: "models", label: "Models", icon: Cpu },
      { id: "sandbox", label: "Sandbox", icon: Terminal },
    ]
  },
  {
    title: "SECURITY",
    items: [
      { id: "access", label: "User Management", icon: Users, adminOnly: true },
      { id: "audit", label: "Audit Ledger", icon: History, adminOnly: true },
      { id: "audit", label: "Audit Verification", icon: CheckCircle2, adminOnly: true },
    ]
  },
  {
    title: "SYSTEM",
    items: [
      { id: "settings", label: "Settings", icon: Settings },
      { id: "settings", label: "About", icon: Info },
    ]
  }
];

interface SidebarProps {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  isMobileDrawer?: boolean;
}

export default function Sidebar({ activeTab, setActiveTab, isMobileDrawer = false }: SidebarProps) {
  const { user, logout } = useAuth();

  // Deduplicate and filter navigation items based on user role privileges
  const filteredCategories = NAVIGATION_CATEGORIES.map((category) => {
    const items = category.items.filter((item) => {
      if (item.adminOnly) {
        return user?.role === "admin";
      }
      return true;
    });

    // Remove duplicate tab labels within category if any
    const uniqueItems: NavigationItem[] = [];
    const seenIds = new Set<string>();
    for (const item of items) {
      if (!seenIds.has(item.label)) {
        seenIds.add(item.label);
        uniqueItems.push(item);
      }
    }

    return { ...category, items: uniqueItems };
  }).filter((category) => category.items.length > 0);

  const containerClasses = isMobileDrawer
    ? "w-[270px] h-full bg-[#070b14] border-r border-slate-800/80 flex flex-col select-none font-sans"
    : "hidden md:flex md:w-[72px] lg:w-[270px] h-full bg-[#070b14] border-r border-slate-800/80 flex-col shrink-0 select-none font-sans transition-all duration-200 shadow-2xl";

  const getInitials = (name?: string) => {
    if (!name) return "AG";
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <aside className={containerClasses}>
      {/* Brand Header */}
      <div className="h-20 px-5 border-b border-slate-800/80 flex items-center bg-[#090e1a]/90 backdrop-blur-xl">
        <div className="flex items-center space-x-3.5 mx-auto lg:mx-0">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-600/20 to-indigo-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0 shadow-lg shadow-blue-500/10">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="flex flex-col lg:flex cursor-default select-none transition-all duration-200" style={{ display: isMobileDrawer ? "flex" : undefined }}>
            <div className="flex items-center space-x-2">
              <span className="text-base font-extrabold tracking-tight text-slate-100 uppercase lg:block hidden font-sans" style={{ display: isMobileDrawer ? "block" : undefined }}>
                AEGIS
              </span>
            </div>
            <span className="text-[11px] text-blue-400/90 tracking-wide uppercase font-semibold lg:block hidden font-sans" style={{ display: isMobileDrawer ? "block" : undefined }}>
              Sovereign AI Workbench
            </span>
            <div className="lg:flex hidden items-center space-x-1.5 mt-1" style={{ display: isMobileDrawer ? "flex" : undefined }}>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[9px] font-bold text-emerald-400/90 tracking-widest uppercase font-mono">
                SYSTEM OPERATIONAL
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Categories and Items */}
      <nav className="flex-1 px-3 py-5 space-y-5 overflow-y-auto">
        {filteredCategories.map((category) => (
          <div key={category.title} className="space-y-1">
            {/* Category Section Label */}
            <div className="px-3 py-1 lg:block hidden" style={{ display: isMobileDrawer ? "block" : undefined }}>
              <span className="text-xs font-bold text-slate-400 tracking-wider uppercase font-sans">
                {category.title}
              </span>
            </div>
            <div className="lg:hidden border-t border-slate-800/80 my-2 mx-2" style={{ display: isMobileDrawer ? "none" : undefined }} />

            <div className="space-y-0.5">
              {category.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;

                return (
                  <button
                    key={item.label}
                    onClick={() => setActiveTab(item.id)}
                    className={`w-full flex items-center lg:space-x-3 px-3 py-2.5 rounded-xl text-sm transition-all cursor-pointer relative justify-center lg:justify-start font-sans ${
                      isActive 
                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/25 font-bold shadow-md shadow-blue-500/5" 
                        : "text-slate-300 hover:bg-slate-800/60 hover:text-slate-100 border border-transparent font-medium"
                    }`}
                    title={item.label}
                  >
                    {/* Left Active Accent Bar */}
                    {isActive && (
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-blue-500 shadow-sm shadow-blue-500" />
                    )}

                    <Icon className={`h-4.5 w-4.5 shrink-0 transition-colors ${isActive ? "text-blue-400" : "text-slate-400"}`} />

                    <span className="lg:block hidden truncate tracking-wide" style={{ display: isMobileDrawer ? "block" : undefined }}>
                      {item.label}
                    </span>

                    {item.adminOnly && (
                      <span className="ml-auto text-xs font-extrabold uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 lg:block hidden" style={{ display: isMobileDrawer ? "block" : undefined }}>
                        ADMIN
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Bottom Profile & Role Footer */}
      <div className="border-t border-slate-800/80 bg-[#090e1a]/90 backdrop-blur-xl p-4">
        {user && (
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 min-w-0">
              <div className="h-9 w-9 rounded-full bg-gradient-to-br from-blue-600/30 to-indigo-600/30 border border-blue-500/40 flex items-center justify-center text-blue-300 font-bold text-xs shrink-0 shadow-md shadow-black/40">
                {getInitials(user.username)}
              </div>
              <div className="flex flex-col min-w-0 lg:flex" style={{ display: isMobileDrawer ? "flex" : undefined }}>
                <span className="text-xs text-slate-100 font-bold truncate tracking-tight" title={user.username}>
                  {user.username}
                </span>
                <span className="text-xs text-slate-400 font-medium capitalize">
                  {user.role === "admin" ? "Administrator" : "Operator"}
                </span>
              </div>
            </div>

            <button
              onClick={logout}
              className="p-2 bg-slate-800/60 hover:bg-rose-500/10 border border-slate-700/60 hover:border-rose-500/30 text-slate-400 hover:text-rose-400 rounded-lg transition-all cursor-pointer lg:block hidden"
              style={{ display: isMobileDrawer ? "block" : undefined }}
              title="Sign Out"
              aria-label="Sign Out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
