"use client";

import React, { useState, useRef, useEffect } from "react";
import AppShell from "../components/layout/AppShell";
import Sidebar, { TabId } from "../components/layout/Sidebar";
import AuthGuard from "../components/layout/AuthGuard";
import { chatApi, ChatResponse } from "../lib/api/chat";
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
  Activity,
  Send,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Compass,
  Link
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  status: "sending" | "success" | "error";
  sources?: Array<{ filename: string; page_number: number }>;
  verification?: string;
  request_id?: string;
  duration_ms?: number;
}

const SAMPLE_QUERIES = [
  { label: "Code Sandbox Task", text: "write python code to compute the first 10 Fibonacci numbers" },
  { label: "Knowledge RAG Search", text: "search company manual for emergency safety procedures" },
  { label: "Scanned Document OCR", text: "analyze scanned document invoice.pdf to extract total fees" }
];

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");

  // Chat conversational state
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll to message bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (activeTab === "chat") {
      scrollToBottom();
    }
  }, [messages, activeTab]);

  const handleSendMessage = async (textToSend: string) => {
    const trimmed = textToSend.trim();
    if (!trimmed || chatLoading) return;

    setChatError(null);
    const userMessageId = `msg_${Date.now()}`;
    const userMsg: Message = {
      id: userMessageId,
      role: "user",
      content: trimmed,
      timestamp: new Date(),
      status: "success"
    };

    const assistantMsgId = `msg_${Date.now() + 1}`;
    const assistantMsgPlaceholder: Message = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      status: "sending"
    };

    setMessages((prev) => [...prev, userMsg, assistantMsgPlaceholder]);
    setInputMessage("");
    setChatLoading(true);

    try {
      const response = await chatApi.sendMessage(trimmed);
      
      setMessages((prev) => 
        prev.map((msg) => 
          msg.id === assistantMsgId 
            ? {
                ...msg,
                content: response.answer,
                status: response.success ? "success" : "error",
                sources: response.sources,
                verification: response.verification,
                request_id: response.request_id,
                duration_ms: response.duration_ms
              }
            : msg
        )
      );
    } catch (err: any) {
      setMessages((prev) => 
        prev.map((msg) => 
          msg.id === assistantMsgId 
            ? {
                ...msg,
                content: err.message || "The sovereign node failed to return a response.",
                status: "error"
              }
            : msg
        )
      );
      setChatError(err.message || "Network request failed.");
    } finally {
      setChatLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(inputMessage);
    }
  };

  const handleRetry = () => {
    // Find the last user message and resubmit
    const userMsgs = messages.filter((m) => m.role === "user");
    if (userMsgs.length > 0) {
      const lastUserMsg = userMsgs[userMsgs.length - 1];
      // Strip last failed assistant message
      setMessages((prev) => prev.slice(0, -1));
      handleSendMessage(lastUserMsg.content);
    }
  };

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
          <div className="flex flex-col h-[calc(100vh-10rem)] max-w-5xl mx-auto border border-white/5 rounded-lg bg-[#0c1220]/60 overflow-hidden relative">
            {/* Conversation view window */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-8 space-y-6 animate-fadeIn">
                  <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 mx-auto">
                    <MessageSquareCode className="h-6 w-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold text-slate-200 font-mono">AEGIS AI Assistant Core</h3>
                    <p className="text-xs text-slate-500 max-w-sm">Submit prompts to compile multi-step agent plans, trigger sandboxes, or search manuals.</p>
                  </div>
                  
                  {/* Sample Triggers */}
                  <div className="grid grid-cols-1 gap-3 max-w-xl w-full pt-4">
                    {SAMPLE_QUERIES.map((q, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          setInputMessage(q.text);
                          handleSendMessage(q.text);
                        }}
                        className="w-full p-3 bg-[#0e1626]/70 hover:bg-[#121c30] border border-white/5 hover:border-blue-500/20 rounded-lg text-left transition-all flex items-center space-x-3 cursor-pointer group"
                      >
                        <Compass className="h-4.5 w-4.5 text-slate-400 group-hover:text-blue-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider block font-mono">{q.label}</span>
                          <span className="text-xs text-slate-350 block truncate font-mono mt-0.5">{q.text}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {messages.map((msg) => {
                    const isUser = msg.role === "user";
                    const formattedTime = msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                    
                    return (
                      <div key={msg.id} className={`flex ${isUser ? "justify-end" : "justify-start"} animate-slideIn`}>
                        <div className={`max-w-[75%] rounded-lg p-4 border relative ${
                          isUser 
                            ? "bg-blue-600/10 border-blue-500/20 text-slate-100" 
                            : "bg-[#0e1626]/80 border-white/5 text-slate-200"
                        }`}>
                          {/* Sending Spinner */}
                          {msg.status === "sending" && (
                            <div className="flex items-center space-x-3 text-slate-400 py-1">
                              <RefreshCw className="h-4 w-4 animate-spin text-blue-400" />
                              <span className="text-xs font-mono tracking-wider">Compiling Agent Execution Steps...</span>
                            </div>
                          )}

                          {/* Message Content */}
                          {msg.status !== "sending" && (
                            <div className="text-xs font-mono leading-relaxed whitespace-pre-wrap">
                              {msg.content}
                            </div>
                          )}

                          {/* RAG Sources Metadata */}
                          {!isUser && msg.sources && msg.sources.length > 0 && (
                            <div className="mt-4 pt-3 border-t border-white/5 space-y-1.5">
                              <div className="text-[9px] font-bold text-slate-500 uppercase tracking-wider font-mono">Retrieved Sources</div>
                              <div className="flex flex-wrap gap-1.5">
                                {msg.sources.map((s, sidx) => (
                                  <div key={sidx} className="flex items-center space-x-1 px-2 py-0.5 bg-blue-500/5 border border-blue-500/10 rounded text-[9px] text-blue-400 font-mono">
                                    <FileText className="h-3 w-3" />
                                    <span className="truncate max-w-[140px]">{s.filename}</span>
                                    <span className="opacity-50">(p. {s.page_number})</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Citation Verification Badges */}
                          {!isUser && msg.status === "success" && (
                            <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-2 text-[9px] font-mono text-slate-500">
                              <div className="flex items-center space-x-1">
                                {msg.verification && msg.verification.includes("PASS") ? (
                                  <div className="flex items-center space-x-1 text-emerald-400 font-semibold bg-emerald-500/5 border border-emerald-500/10 px-1.5 py-0.5 rounded">
                                    <CheckCircle2 className="h-3 w-3" />
                                    <span>Grounded Claims</span>
                                  </div>
                                ) : (
                                  <div className="flex items-center space-x-1 text-rose-400 font-semibold bg-rose-500/5 border border-rose-500/10 px-1.5 py-0.5 rounded">
                                    <XCircle className="h-3 w-3" />
                                    <span>Unverified Claims</span>
                                  </div>
                                )}
                              </div>
                              {msg.duration_ms && (
                                <span>Elapsed: {msg.duration_ms}ms</span>
                              )}
                            </div>
                          )}

                          {/* Request Correlation Token */}
                          {msg.request_id && (
                            <div className="mt-2 text-right">
                              <span className="text-[8px] font-mono text-slate-600 select-all" title="Click to select correlation ID">
                                REF: {msg.request_id}
                              </span>
                            </div>
                          )}
                          
                          {/* Clock Ticker */}
                          <div className="text-[8px] text-slate-550 text-right mt-1.5 font-mono">
                            {formattedTime}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>

            {/* Error Actions drawer */}
            {chatError && (
              <div className="bg-rose-500/5 border-y border-rose-500/15 p-3 flex items-center justify-between px-6">
                <div className="flex items-center space-x-2 text-rose-400 text-xs font-mono">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>Agent Execution Error: {chatError}</span>
                </div>
                <button
                  onClick={handleRetry}
                  className="flex items-center space-x-1 text-xs text-rose-400 hover:text-rose-300 font-mono bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 px-2.5 py-1 rounded transition-colors cursor-pointer"
                >
                  <RefreshCw className="h-3 w-3" />
                  <span>Retry Send</span>
                </button>
              </div>
            )}

            {/* Input submission container */}
            <div className="p-4 border-t border-white/5 bg-[#0a0f1d]/50">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSendMessage(inputMessage);
                }}
                className="flex items-end space-x-3"
              >
                <div className="flex-1 relative">
                  <textarea
                    rows={2}
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyDown={handleKeyDown}
                    maxLength={1000}
                    placeholder="Ask the sovereign agent (e.g. 'write python code...')"
                    disabled={chatLoading}
                    className="w-full px-4 py-3 bg-[#0e1626]/75 border border-white/5 focus:border-blue-500/40 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none transition-all resize-none font-mono disabled:opacity-50"
                  />
                  <div className="absolute right-3 bottom-2.5 text-[8px] font-mono text-slate-600">
                    {inputMessage.length}/1000 chars
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={!inputMessage.trim() || chatLoading}
                  className="h-10 w-10 shrink-0 bg-blue-600 hover:bg-blue-500 border border-blue-500/20 rounded-lg flex items-center justify-center text-white transition-colors cursor-pointer disabled:opacity-30 disabled:bg-blue-600/10"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
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
              <div className="h-12 w-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-405">
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
