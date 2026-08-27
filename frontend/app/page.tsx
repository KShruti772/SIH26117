"use client";

import React, { useState } from "react";
import AppShell from "../components/layout/AppShell";
import Sidebar, { TabId } from "../components/layout/Sidebar";
import AuthGuard from "../components/layout/AuthGuard";
import { 
  ShieldCheck, 
  Terminal, 
  Cpu, 
  Database, 
  History, 
  Lock, 
  FileText, 
  HardDrive, 
  Settings as SettingsIcon,
  MessageSquareCode,
  Activity
} from "lucide-react";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");

  // Helper to render active tab content
  const renderContent = () => {
    switch (activeTab) {
      case "dashboard":
        return (
          <div className="space-y-8 animate-fadeIn">
            {/* Page Header */}
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 font-mono">Sovereign Node Dashboard</h1>
              <p className="text-sm text-slate-400 mt-1 font-mono">Real-time status overview of local AI operations and security layers.</p>
            </div>

            {/* Hardware Constraints Banner */}
            <div className="bg-[#1e293b]/30 border border-blue-500/20 rounded-lg p-6 flex flex-col md:flex-row md:items-center md:justify-between space-y-4 md:space-y-0">
              <div className="flex items-start space-x-4">
                <div className="p-2.5 bg-blue-500/10 border border-blue-500/30 rounded text-blue-400 shrink-0">
                  <HardDrive className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-200 font-mono">Workstation VRAM Boundary Active</h3>
                  <p className="text-xs text-slate-400 mt-1 max-w-xl">
                    Dynamic Loader enforces a single-active-model constraint. Swapping models releases GPU memory automatically to fit within the local target NVIDIA RTX 4050 6GB limit.
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-2 font-mono text-xs px-3 py-1.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 self-start md:self-auto">
                <Activity className="h-4 w-4 animate-pulse" />
                <span>6.0 GB VRAM CAP</span>
              </div>
            </div>

            {/* Core Capabilities Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Card 1: Dynamic Model Loader */}
              <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-6 hover:border-blue-500/25 transition-all">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-purple-500/10 border border-purple-500/25 rounded text-purple-400">
                      <Cpu className="h-5 w-5" />
                    </div>
                    <span className="text-sm font-semibold text-slate-200 font-mono">Dynamic Model Loader</span>
                  </div>
                  <span className="text-[10px] font-mono uppercase bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                    Verified
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Handles dynamic loading, VRAM allocation swapping, and cache routing for local open-weight LLMs (Qwen, Gemma, Llama).
                </p>
                <div className="text-[10px] font-mono text-slate-500 border-t border-white/5 pt-3 flex justify-between">
                  <span>Runtime: Ollama (Local)</span>
                  <span>Swaps: Mutex Locked</span>
                </div>
              </div>

              {/* Card 2: Isolated Code Execution Sandbox */}
              <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-6 hover:border-blue-500/25 transition-all">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-yellow-500/10 border border-yellow-500/25 rounded text-yellow-400">
                      <Terminal className="h-5 w-5" />
                    </div>
                    <span className="text-sm font-semibold text-slate-200 font-mono">Python Code Sandbox</span>
                  </div>
                  <span className="text-[10px] font-mono uppercase bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                    Verified
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Executes dynamically generated coding scripts in an isolated process with strict environment scrubbing and timeout limits.
                </p>
                <div className="text-[10px] font-mono text-slate-500 border-t border-white/5 pt-3 flex justify-between">
                  <span>Isolation: Subprocess</span>
                  <span>Timeout limit: 10s</span>
                </div>
              </div>

              {/* Card 3: Local Knowledge & RAG */}
              <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-6 hover:border-blue-500/25 transition-all">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-blue-500/10 border border-blue-500/25 rounded text-blue-400">
                      <Database className="h-5 w-5" />
                    </div>
                    <span className="text-sm font-semibold text-slate-200 font-mono">Local Knowledge / RAG</span>
                  </div>
                  <span className="text-[10px] font-mono uppercase bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                    Verified
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Indexes PDF/TXT documents, computes vector coordinates, and queries similarity matches locally using ChromaDB.
                </p>
                <div className="text-[10px] font-mono text-slate-500 border-t border-white/5 pt-3 flex justify-between">
                  <span>Vector DB: ChromaDB (Local)</span>
                  <span>Ingestion: Recursive</span>
                </div>
              </div>

              {/* Card 4: Audit Logging Ledger */}
              <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-6 hover:border-blue-500/25 transition-all">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-rose-500/10 border border-rose-500/25 rounded text-rose-400">
                      <History className="h-5 w-5" />
                    </div>
                    <span className="text-sm font-semibold text-slate-200 font-mono">Audit Logging Ledger</span>
                  </div>
                  <span className="text-[10px] font-mono uppercase bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                    Verified
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed mb-4">
                  Append-only SQLite logs track model swaps, sandboxes, and authentication actions under context-based request correlation.
                </p>
                <div className="text-[10px] font-mono text-slate-500 border-t border-white/5 pt-3 flex justify-between">
                  <span>Audit DB: SQLite3</span>
                  <span>Encryption: Salted Bcrypt</span>
                </div>
              </div>
            </div>
          </div>
        );

      case "chat":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <MessageSquareCode className="h-5 w-5 text-blue-400" />
              <span>AI Assistant</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                The agent planning controller is configured. Direct chat UI triggers and socket pipelines will be fully mounted in the next integration task.
              </p>
            </div>
          </div>
        );

      case "rag":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <Database className="h-5 w-5 text-blue-400" />
              <span>Knowledge / RAG Ingestion</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Local vectors, document extraction layouts, and Chroma DB instances are verified. The upload dashboard will be mounted in a future integration step.
              </p>
            </div>
          </div>
        );

      case "documents":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <FileText className="h-5 w-5 text-blue-400" />
              <span>Deliverables / Generated Documents</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Word (.docx), Spreadsheet (.xlsx), and PDF compilers are verified backend modules. The generated deliverables browser will be linked in a future task.
              </p>
            </div>
          </div>
        );

      case "models":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <Cpu className="h-5 w-5 text-blue-400" />
              <span>Dynamic Model Swapper</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Memory allocation switches, model metadata configuration displays, and Ollama weight swappers are configured. Controls will be active in future integrations.
              </p>
            </div>
          </div>
        );

      case "sandbox":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <Terminal className="h-5 w-5 text-blue-400" />
              <span>Isolated Code Sandbox</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Python subprocess isolation, standard streams interception, and environment scrubbing are active backend layers. Interactive scratchpads will mount in a future task.
              </p>
            </div>
          </div>
        );

      case "audit":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <History className="h-5 w-5 text-blue-400" />
              <span>System Audit Logs Ledger</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                The append-only database logs are configured and run in background tasks. Log viewers for administrators will be fully integrated in the next authentication task.
              </p>
            </div>
          </div>
        );

      case "settings":
        return (
          <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
            <h1 className="text-xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
              <SettingsIcon className="h-5 w-5 text-blue-400" />
              <span>System Settings</span>
            </h1>
            <div className="bg-[#0e1626]/60 border border-white/5 rounded-lg p-8 text-center space-y-4">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                <Lock className="h-6 w-6" />
              </div>
              <h3 className="text-md font-semibold text-slate-200 font-mono">Module Sealed</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Sovereign environment variables are loaded directly from the system backend. Advanced configurations panel controls will mount in a future task.
              </p>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <AuthGuard>
      <AppShell activeTab={activeTab} setActiveTab={setActiveTab}>
        {renderContent()}
      </AppShell>
    </AuthGuard>
  );
}
