"use client";

import React from "react";
import { 
  Shield, 
  LayoutDashboard, 
  MessageSquareCode, 
  Database, 
  FileSpreadsheet, 
  Cpu, 
  Terminal, 
  History, 
  Settings 
} from "lucide-react";

export type TabId = 
  | "dashboard"
  | "chat"
  | "rag"
  | "documents"
  | "models"
  | "sandbox"
  | "audit"
  | "settings";

interface NavigationItem {
  id: TabId;
  label: string;
  icon: React.ComponentType<any>;
}

interface SidebarProps {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
}

const NAVIGATION_ITEMS: NavigationItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "chat", label: "AI Assistant", icon: MessageSquareCode },
  { id: "rag", label: "Knowledge / RAG", icon: Database },
  { id: "documents", label: "Documents", icon: FileSpreadsheet },
  { id: "models", label: "Models", icon: Cpu },
  { id: "sandbox", label: "Sandbox", icon: Terminal },
  { id: "audit", label: "Audit Logs", icon: History },
  { id: "settings", label: "Settings", icon: Settings },
];

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  return (
    <aside className="w-[260px] bg-[#0c1220] border-r border-white/5 flex flex-col shrink-0">
      {/* Brand Header */}
      <div className="h-16 px-6 border-b border-white/5 flex items-center space-x-3">
        <div className="h-8 w-8 rounded bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
          <Shield className="h-5 w-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-bold tracking-wider text-slate-100 font-mono">AEGIS // WORKBENCH</span>
          <span className="text-[10px] text-slate-500 tracking-wider">Air-Gapped Sovereign Node</span>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 px-4 py-6 space-y-1">
        {NAVIGATION_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all cursor-pointer ${
                isActive 
                  ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" 
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-200 border border-transparent"
              }`}
            >
              <Icon className={`h-4.5 w-4.5 ${isActive ? "text-blue-400" : "text-slate-400"}`} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-4 border-t border-white/5 bg-black/10">
        <div className="text-[10px] font-mono text-slate-500 text-center space-y-1">
          <div>SIH PROBLEM STATEMENT 26117</div>
          <div className="text-blue-500/40">Secure Node v0.1.0</div>
        </div>
      </div>
    </aside>
  );
}
