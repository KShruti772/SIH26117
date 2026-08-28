"use client";

import React, { useState, useRef, useEffect } from "react";
import AppShell from "../components/layout/AppShell";
import Sidebar, { TabId } from "../components/layout/Sidebar";
import AuthGuard from "../components/layout/AuthGuard";
import { chatApi, ChatResponse } from "../lib/api/chat";
import { ragApi, DocumentInfo } from "../lib/api/rag";
import { modelsApi, ModelProfile } from "../lib/api/models";
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
  Link,
  Upload,
  Trash2,
  AlertTriangle
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
  
  // RAG / Knowledge Base states
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  
  const [reindexingDocId, setReindexingDocId] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);

  // Model management states
  const [modelRegistry, setModelRegistry] = useState<ModelProfile[]>([]);
  const [currentModel, setCurrentModel] = useState<ModelProfile | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [swappingModelId, setSwappingModelId] = useState<string | null>(null);
  const [swapMessage, setSwapMessage] = useState<{ type: "success" | "info" | "error"; text: string } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto scroll to message bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (activeTab === "chat") {
      scrollToBottom();
    }
  }, [messages, activeTab]);

  // Load documents when RAG tab is selected
  const loadDocuments = async () => {
    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      const docs = await ragApi.listDocuments();
      setDocuments(docs);
    } catch (err: any) {
      setDocumentsError(err.message || "Failed to load knowledge base documents.");
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "rag") {
      loadDocuments();
      // Reset upload card state
      setSelectedFile(null);
      setUploadSuccess(null);
      setUploadError(null);
    }
  }, [activeTab]);

  const loadModelsData = async () => {
    setModelsLoading(true);
    setModelsError(null);
    setSwapMessage(null);
    try {
      const [registry, current] = await Promise.all([
        modelsApi.listRegistry(),
        modelsApi.getCurrentModel()
      ]);
      setModelRegistry(registry);
      setCurrentModel(current);
    } catch (err: any) {
      setModelsError(err.message || "Failed to load dynamic models registry.");
    } finally {
      setModelsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "models") {
      loadModelsData();
    }
  }, [activeTab]);

  const handleSelectModel = async (modelId: string) => {
    if (swappingModelId || modelsLoading) return;
    setSwappingModelId(modelId);
    setSwapMessage({ type: "info", text: "Swapping models. Releasing previous VRAM cache and loading weights..." });
    try {
      const res = await modelsApi.switchModel(modelId);
      const updatedCurrent = await modelsApi.getCurrentModel();
      setCurrentModel(updatedCurrent);
      if (res.details === "simulated_load" || res.warning) {
        setSwapMessage({
          type: "success",
          text: "Simulated swap success. Warning: local Ollama runtime is offline. System is running in offline simulated mock inference mode."
        });
      } else {
        setSwapMessage({
          type: "success",
          text: `Successfully swapped to model '${modelId}'! Weights loaded in memory.`
        });
      }
    } catch (err: any) {
      setSwapMessage({
        type: "error",
        text: err.message || "VRAM allocation or dynamic model load failed."
      });
    } finally {
      setSwappingModelId(null);
    }
  };

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
    const userMsgs = messages.filter((m) => m.role === "user");
    if (userMsgs.length > 0) {
      const lastUserMsg = userMsgs[userMsgs.length - 1];
      setMessages((prev) => prev.slice(0, -1));
      handleSendMessage(lastUserMsg.content);
    }
  };

  // Upload file execution
  const handleUploadFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || uploading) return;

    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      // Extra client validations (Ponytail double check)
      if (selectedFile.size === 0) {
        throw new Error("Empty files cannot be indexed.");
      }
      if (selectedFile.size > 10 * 1024 * 1024) {
        throw new Error("File exceeds maximum allowed size of 10MB.");
      }
      const ext = selectedFile.name.split(".").pop()?.toLowerCase();
      if (ext !== "pdf" && ext !== "txt") {
        throw new Error("Unsupported format. Please upload PDF or TXT.");
      }

      const res = await ragApi.ingestDocument(selectedFile);
      setUploadSuccess(`Ingested '${res.filename}' successfully! Calculated vector fragments.`);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      
      // Reload list
      await loadDocuments();
    } catch (err: any) {
      setUploadError(err.message || "Upload or indexing failed.");
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
      setUploadError(null);
      setUploadSuccess(null);
    }
  };

  const handleReindex = async (id: string) => {
    if (reindexingDocId || deletingDocId) return;
    setReindexingDocId(id);
    try {
      await ragApi.reindexDocument(id);
      await loadDocuments();
    } catch (err: any) {
      alert(err.message || "Manual re-indexing operation failed.");
    } finally {
      setReindexingDocId(null);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (reindexingDocId || deletingDocId) return;
    if (!confirm(`Are you sure you want to permanently delete document '${name}' from vector DB indexes and disk?`)) {
      return;
    }
    setDeletingDocId(id);
    try {
      await ragApi.deleteDocument(id);
      await loadDocuments();
    } catch (err: any) {
      alert(err.message || "Failed to delete document.");
    } finally {
      setDeletingDocId(null);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
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
          <div className="max-w-5xl mx-auto space-y-6 animate-fadeIn">
            {/* RAG Header */}
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
                <Database className="h-6 w-6 text-blue-400" />
                <span>Knowledge Base Ingestion</span>
              </h1>
              <p className="text-sm text-slate-400 mt-1 font-mono">Upload and index reference documents in the local vector DB to ground AI planning.</p>
            </div>

            {/* Security boundaries note */}
            <div className="bg-amber-500/5 border border-amber-500/15 rounded-lg p-4 flex items-start space-x-3 text-amber-400 font-mono text-xs">
              <AlertTriangle className="h-4.5 w-4.5 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold uppercase tracking-wide">Confidentiality Guard Warning:</span>
                <p className="mt-1 text-slate-350 leading-relaxed">
                  Document-level authorization boundaries are currently global in the MVP vector database. All ingested documents are searchable by standard users. Avoid uploading personal database tokens or root-level server access credentials.
                </p>
              </div>
            </div>

            {/* Document Ingestion Forms & Table Workspace */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
              
              {/* Left Column: Upload card */}
              <div className="lg:col-span-1 bg-[#0e1626]/70 border border-white/5 rounded-lg p-5 space-y-4">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider font-mono">Ingest New File</h3>
                
                <form onSubmit={handleUploadFile} className="space-y-4">
                  {/* Custom Drag Drop Zone */}
                  <div 
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-white/10 hover:border-blue-500/30 rounded-lg p-6 text-center cursor-pointer transition-all bg-[#0a0f1d]/40 group"
                  >
                    <input 
                      type="file" 
                      ref={fileInputRef}
                      onChange={handleFileChange}
                      accept=".txt,.pdf"
                      className="hidden"
                    />
                    <Upload className="h-8 w-8 text-slate-500 group-hover:text-blue-400 mx-auto transition-colors" />
                    <span className="text-xs text-slate-400 font-semibold block font-mono mt-3">Select Document file</span>
                    <span className="text-[10px] text-slate-650 block font-mono mt-1">PDF or TXT formats (Max 10MB)</span>
                  </div>

                  {/* Selected File Details */}
                  {selectedFile && (
                    <div className="p-3 bg-[#0a0f1d]/50 border border-white/5 rounded flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-semibold text-slate-200 block truncate font-mono">{selectedFile.name}</span>
                        <span className="text-[10px] text-slate-500 block font-mono mt-0.5">{formatBytes(selectedFile.size)}</span>
                      </div>
                      <button 
                        type="button"
                        onClick={() => setSelectedFile(null)}
                        className="text-[10px] font-bold text-slate-500 hover:text-slate-300 font-mono ml-2 cursor-pointer"
                      >
                        Clear
                      </button>
                    </div>
                  )}

                  {/* Submit upload button */}
                  <button
                    type="submit"
                    disabled={!selectedFile || uploading}
                    className="w-full h-9 bg-blue-600 hover:bg-blue-500 border border-blue-500/20 text-white rounded text-xs font-mono font-semibold transition-colors flex items-center justify-center space-x-2 cursor-pointer disabled:opacity-40 disabled:bg-blue-600/10"
                  >
                    {uploading ? (
                      <>
                        <RefreshCw className="h-4.5 w-4.5 animate-spin" />
                        <span>Parsing & Vectorizing...</span>
                      </>
                    ) : (
                      <span>Upload & Index</span>
                    )}
                  </button>
                </form>

                {/* Alerts alerts */}
                {uploadSuccess && (
                  <div className="bg-emerald-500/5 border border-emerald-500/15 p-3 rounded flex items-start space-x-2 text-emerald-400 text-[10px] font-mono leading-relaxed">
                    <CheckCircle2 className="h-4.5 w-4.5 shrink-0 mt-0.5" />
                    <span>{uploadSuccess}</span>
                  </div>
                )}

                {uploadError && (
                  <div className="bg-rose-500/5 border border-rose-500/15 p-3 rounded flex items-start space-x-2 text-rose-400 text-[10px] font-mono leading-relaxed">
                    <AlertCircle className="h-4.5 w-4.5 shrink-0 mt-0.5" />
                    <span>Indexing Error: {uploadError}</span>
                  </div>
                )}
              </div>

              {/* Right Column: Documents table */}
              <div className="lg:col-span-2 bg-[#0e1626]/70 border border-white/5 rounded-lg p-5 space-y-4 overflow-hidden">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider font-mono">Indexed Documents</h3>
                  <button
                    onClick={loadDocuments}
                    disabled={documentsLoading}
                    className="p-1.5 rounded hover:bg-white/5 text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                  >
                    <RefreshCw className={`h-4.5 w-4.5 ${documentsLoading ? "animate-spin text-blue-400" : ""}`} />
                  </button>
                </div>

                {documentsError && (
                  <div className="bg-rose-500/5 border border-rose-500/15 p-3 rounded text-rose-400 text-xs font-mono">
                    {documentsError}
                  </div>
                )}

                {/* Documents Table layout */}
                {documentsLoading && documents.length === 0 ? (
                  <div className="text-center py-12 text-xs text-slate-500 font-mono">
                    Fetching vector database documents listing...
                  </div>
                ) : documents.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-white/5 rounded-lg text-xs text-slate-500 font-mono space-y-2">
                    <FileText className="h-8 w-8 text-slate-655 mx-auto opacity-40" />
                    <p>No knowledge base documents currently ingested.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-mono text-[11px] text-slate-300">
                      <thead>
                        <tr className="border-b border-white/5 text-slate-500 uppercase tracking-wider text-[9px] font-bold">
                          <th className="py-2.5 px-3">Filename</th>
                          <th className="py-2.5 px-3">Status</th>
                          <th className="py-2.5 px-3">Ingested At</th>
                          <th className="py-2.5 px-3 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {documents.map((doc) => (
                          <tr key={doc.id} className="hover:bg-white/5 transition-colors">
                            <td className="py-3 px-3 truncate max-w-[200px]" title={doc.filename}>
                              {doc.filename}
                            </td>
                            <td className="py-3 px-3">
                              <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/10 text-[9px]">
                                {doc.status}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-slate-500">
                              {new Date(doc.uploaded_at * 1000).toLocaleString()}
                            </td>
                            <td className="py-3 px-3 text-right space-x-2">
                              {/* Manual Reindex */}
                              <button
                                onClick={() => handleReindex(doc.id)}
                                disabled={reindexingDocId !== null || deletingDocId !== null}
                                className="px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/15 rounded text-slate-450 hover:text-slate-200 transition-all cursor-pointer disabled:opacity-40"
                              >
                                {reindexingDocId === doc.id ? "Index..." : "Re-Index"}
                              </button>
                              {/* Permanent Delete */}
                              <button
                                onClick={() => handleDelete(doc.id, doc.filename)}
                                disabled={reindexingDocId !== null || deletingDocId !== null}
                                className="p-1 text-rose-500 hover:text-rose-400 hover:bg-rose-500/10 rounded border border-rose-500/10 hover:border-rose-500/20 transition-all cursor-pointer disabled:opacity-40 inline-flex items-center"
                              >
                                {deletingDocId === doc.id ? (
                                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Trash2 className="h-3.5 w-3.5" />
                                )}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
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
          <div className="max-w-5xl mx-auto space-y-6 animate-fadeIn">
            {/* Models Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-slate-100 font-mono flex items-center space-x-2">
                  <Cpu className="h-6 w-6 text-blue-400" />
                  <span>Dynamic Model Swapper</span>
                </h1>
                <p className="text-sm text-slate-400 mt-1 font-mono">Manage and select local AI open-weight models loaded into workstation VRAM.</p>
              </div>
              <button
                onClick={loadModelsData}
                disabled={modelsLoading}
                className="p-1.5 rounded hover:bg-white/5 text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
              >
                <RefreshCw className={`h-4.5 w-4.5 ${modelsLoading ? "animate-spin text-blue-400" : ""}`} />
              </button>
            </div>

            {/* Error alerts */}
            {modelsError && (
              <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg text-rose-400 text-xs font-mono">
                Error Loading Registry: {modelsError}
              </div>
            )}

            {/* Swapping swap status alerts */}
            {swapMessage && (
              <div className={`p-4 border rounded-lg text-xs font-mono flex items-start space-x-3 ${
                swapMessage.type === "info" 
                  ? "bg-blue-500/5 border-blue-500/15 text-blue-450"
                  : swapMessage.type === "success"
                  ? "bg-emerald-500/5 border-emerald-500/15 text-emerald-450"
                  : "bg-rose-500/5 border-rose-500/15 text-rose-450"
              }`}>
                {swapMessage.type === "info" && <RefreshCw className="h-4 w-4 shrink-0 mt-0.5 animate-spin text-blue-400" />}
                {swapMessage.type === "success" && <CheckCircle2 className="h-4.5 w-4.5 shrink-0 mt-0.5 text-emerald-400" />}
                {swapMessage.type === "error" && <AlertCircle className="h-4.5 w-4.5 shrink-0 mt-0.5 text-rose-400" />}
                <span>{swapMessage.text}</span>
              </div>
            )}

            {/* Top row layout: VRAM Gauge and Active model view */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              
              {/* Active Model card */}
              <div className="md:col-span-2 bg-[#0e1626]/70 border border-white/5 rounded-lg p-5 space-y-4">
                <h3 className="text-xs font-bold text-slate-450 uppercase tracking-wider font-mono">Current Active Model</h3>
                {currentModel ? (
                  <div className="space-y-4">
                    <div>
                      <span className="text-lg font-bold text-slate-100 font-mono block">{currentModel.display_name}</span>
                      <span className="text-[10px] text-slate-500 font-mono block mt-1">ID: {currentModel.model_id} | Provider: {currentModel.provider}</span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 font-mono text-[11px] text-slate-350 border-t border-white/5 pt-4">
                      <div>
                        <span className="text-slate-550 block">Quantization:</span>
                        <span className="font-semibold text-slate-200">{currentModel.quantization}</span>
                      </div>
                      <div>
                        <span className="text-slate-550 block">Context Length:</span>
                        <span className="font-semibold text-slate-200">{currentModel.context_length.toLocaleString()} tokens</span>
                      </div>
                      <div>
                        <span className="text-slate-550 block">VRAM Usage:</span>
                        <span className="font-semibold text-slate-200">{currentModel.estimated_vram_gb} GB</span>
                      </div>
                      <div>
                        <span className="text-slate-550 block">Status:</span>
                        <span className="text-emerald-400 font-semibold">{currentModel.status}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-6 text-xs text-slate-500 font-mono">
                    No active model resolved. Select a model below to load.
                  </div>
                )}
              </div>

              {/* VRAM constraints Gauge */}
              <div className="bg-[#0e1626]/70 border border-white/5 rounded-lg p-5 flex flex-col justify-between space-y-4">
                <div>
                  <h3 className="text-xs font-bold text-slate-450 uppercase tracking-wider font-mono">VRAM Memory Allocation</h3>
                  <p className="text-[10px] text-slate-500 font-mono mt-1">NVIDIA RTX 4050 6GB Workstation constraints.</p>
                </div>
                
                {/* Progress bar */}
                <div className="space-y-2">
                  <div className="flex justify-between font-mono text-xs">
                    <span className="text-slate-400">Used VRAM:</span>
                    <span className="font-bold text-slate-250">{currentModel ? `${currentModel.estimated_vram_gb} GB` : "0.0 GB"} / 6.0 GB</span>
                  </div>
                  <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-blue-600 rounded-full transition-all duration-500"
                      style={{ width: `${currentModel ? (currentModel.estimated_vram_gb / 6.0) * 100 : 0}%` }}
                    />
                  </div>
                </div>

                <div className="text-[9px] font-mono text-slate-550 leading-relaxed border-t border-white/5 pt-3">
                  Loader lock guarantees mutex safety by unloading active weights before swapping memory.
                </div>
              </div>
            </div>

            {/* List of Models in Registry */}
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-slate-350 uppercase tracking-wider font-mono">Available Model Registry</h3>
              
              {modelsLoading && modelRegistry.length === 0 ? (
                <div className="text-center py-12 text-xs text-slate-550 font-mono">
                  Loading model profiles...
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {modelRegistry.map((model) => {
                    const isActive = currentModel?.model_id === model.model_id;
                    const isSwapping = swappingModelId === model.model_id;

                    return (
                      <div 
                        key={model.model_id}
                        className={`bg-[#0c1220]/75 border rounded-lg p-5 flex flex-col justify-between space-y-4 hover:border-blue-500/25 transition-all ${
                          isActive ? "border-blue-500/35 ring-1 ring-blue-500/10" : "border-white/5"
                        }`}
                      >
                        <div>
                          <div className="flex items-start justify-between">
                            <span className="text-xs font-bold text-slate-200 font-mono block truncate max-w-[170px]" title={model.display_name}>
                              {model.display_name}
                            </span>
                            {isActive && (
                              <span className="text-[8px] font-bold font-mono uppercase bg-blue-500/15 text-blue-400 border border-blue-500/25 px-1.5 py-0.5 rounded">
                                Active
                              </span>
                            )}
                          </div>
                          <span className="text-[9px] text-slate-500 font-mono block mt-1">Type: {model.model_type} | VRAM: {model.estimated_vram_gb} GB</span>
                          
                          {/* Capability Badges */}
                          <div className="flex flex-wrap gap-1 mt-3">
                            {model.capabilities.map((cap) => (
                              <span 
                                key={cap}
                                className="text-[8px] font-mono bg-white/5 text-slate-400 px-1.5 py-0.5 rounded border border-white/5"
                              >
                                {cap}
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Action buttons */}
                        <button
                          onClick={() => handleSelectModel(model.model_id)}
                          disabled={isActive || swappingModelId !== null || modelsLoading}
                          className={`w-full h-8 rounded text-[10px] font-mono font-semibold transition-all flex items-center justify-center space-x-1.5 cursor-pointer ${
                            isActive 
                              ? "bg-blue-500/5 text-blue-400 border border-blue-500/20 cursor-default"
                              : "bg-[#0e1626] border border-white/10 text-slate-300 hover:text-slate-100 hover:bg-[#121c30] hover:border-blue-500/20 disabled:opacity-40"
                          }`}
                        >
                          {isSwapping ? (
                            <>
                              <RefreshCw className="h-3 w-3 animate-spin" />
                              <span>Swapping...</span>
                            </>
                          ) : isActive ? (
                            <span>Currently Loaded</span>
                          ) : (
                            <>
                              <Cpu className="h-3 w-3" />
                              <span>Activate Model</span>
                            </>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
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
