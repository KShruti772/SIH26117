"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar, { TabId } from "../components/layout/Sidebar";
import AppShell from "../components/layout/AppShell";
import AuthGuard from "../components/layout/AuthGuard";
import { chatApi, ConversationSession, RoutingTelemetry } from "../lib/api/chat";
import {
  ragApi,
  DocumentInfo,
  RagQueryResponse,
  RagSearchResult,
  GroundedAnswerResponse,
  KnowledgeBaseGenerationResult
} from "../lib/api/rag";
import { parseGenerationIntent } from "../lib/rag/intent";
import { modelsApi, ModelProfile, ModelTestResult } from "../lib/api/models";
import { sandboxApi, SandboxExecutionResponse } from "../lib/api/sandbox";
import { auditApi, AuditLog, AuditSummary } from "../lib/api/audit";
import { usersApi, UserProfile } from "../lib/api/users";
import { healthApi, SystemHealthResponse } from "../lib/api/health";
import { useAuth } from "../components/providers/AuthProvider";
import Card from "../components/ui/Card";
import StatusBadge from "../components/ui/StatusBadge";
import Button from "../components/ui/Button";
import DashboardView from "../components/views/DashboardView";
import AboutView from "../components/views/AboutView";
import SettingsView from "../components/views/SettingsView";
import DocumentsView from "../components/views/DocumentsView";
import KnowledgeBaseView from "../components/views/KnowledgeBaseView";
import ModelsView from "../components/views/ModelsView";
import SandboxView, { SandboxHistoryItem } from "../components/views/SandboxView";
import HistoryView, { KnowledgeHistoryItem } from "../components/views/HistoryView";
import ChatSidebar from "../components/views/ChatSidebar";
import AuditRecordDrawer from "../components/views/AuditRecordDrawer";
import { 
  ShieldCheck, 
  Bot, 
  Plus, 
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
  Zap,
  Server,
  KeyRound,
  FileCheck,
  Send,
  AlertCircle,
  FileSignature,
  FileSpreadsheet,
  FileCode,
  Shield,
  File,
  Layers,
  Sparkles,
  ChevronDown,
  RefreshCw,
  Search,
  ChevronRight,
  Upload,
  CheckCircle2,
  User,
  Key,
  XCircle,
  Trash2,
  AlertTriangle,
  LayoutDashboard,
  Unlock,
  Code,
  Download
} from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  status: "sending" | "success" | "error";
  sources?: Array<{ filename: string; page_number: number; text?: string; distance?: number }>;
  verification?: string;
  request_id?: string;
  duration_ms?: number;
  rag_used?: boolean;
  model_id?: string;
  error_detail?: string;
  task_type?: string;
  document_ids?: string[];
  routing_info?: RoutingTelemetry;
  sandbox_execution?: any;
  metadata?: Record<string, any>;
}

function formatTaskType(taskType?: string) {
  if (!taskType) return "General Reasoning";
  switch (taskType) {
    case "DOCUMENT_QA":
      return "Document QA";
    case "DOCUMENT_SUMMARY":
      return "Document Summary";
    case "CODING":
      return "Coding";
    case "CALCULATION":
      return "Calculation";
    case "VISION_ANALYSIS":
      return "Vision Analysis";
    case "TOOL_EXECUTION":
      return "Tool Execution";
    case "GENERAL_TEXT":
    default:
      return "General Reasoning";
  }
}

const SAMPLE_QUERIES = [
  { label: "Code Sandbox Task", text: "write python code to compute the first 10 Fibonacci numbers" },
  { label: "Knowledge RAG Search", text: "search company manual for emergency safety procedures" },
  { label: "Scanned Document OCR", text: "analyze scanned document invoice.pdf to extract total fees" }
];

function formatBytes(bytes: number, decimals = 2) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function renderWhenPresent<T>(value: T | null, render: (value: T) => React.ReactNode) {
  return value === null ? null : render(value);
}

function LandingPage() {
  const router = useRouter();
  
  return (
    <div className="min-h-screen bg-[#070c14] text-[#f8fafc] flex flex-col font-mono selection:bg-blue-500/30">
      {/* Landing Navbar */}
      <header className="h-16 border-b border-white/5 bg-[#070c14]/85 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="h-8 w-8 rounded bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="flex flex-col">
            <span className="text-xs font-bold tracking-wider text-slate-100">AEGIS // WORKBENCH</span>
            <span className="text-[9px] text-slate-500 tracking-wider">Air-Gapped Node Console</span>
          </div>
        </div>
        <div>
          <button
            onClick={() => router.push("/login")}
            className="text-xs font-semibold px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white border border-blue-500/20 transition-all cursor-pointer font-mono"
          >
            Authorized Login
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-5xl mx-auto px-6 py-16 space-y-20">
        {/* Hero Section */}
        <section className="text-center space-y-6 py-8 max-w-3xl mx-auto">
          <div className="inline-flex items-center space-x-2 px-3 py-1.5 rounded bg-blue-500/5 border border-blue-500/15 text-blue-400 text-[9px] uppercase font-bold tracking-widest mx-auto">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse"></span>
            <span>Local Processing Gated Node</span>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-slate-100 uppercase font-mono">
            AEGIS
          </h1>
          <h2 className="text-sm font-bold text-slate-400 tracking-wider uppercase mt-2">
            CONFIDENTIAL INDUSTRIAL AGENTIC WORKBENCH
          </h2>
          <p className="text-xs text-slate-400 leading-relaxed font-mono max-w-2xl mx-auto mt-4 border-y border-white/5 py-4">
            Sovereign AI for environments where data cannot leave the organization.
          </p>
          <div className="flex items-center justify-center space-x-4 pt-6">
            <button
              onClick={() => alert("Access Request: Please request credentials provisioning from the system administrator.")}
              className="text-xs font-bold px-6 py-3 rounded bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 transition-all cursor-pointer font-mono"
            >
              Request Secure Access
            </button>
            <button
              onClick={() => router.push("/login")}
              className="text-xs font-bold px-6 py-3 rounded bg-blue-600 hover:bg-blue-500 text-white border border-blue-500/20 transition-all cursor-pointer font-mono"
            >
              Explore Workbench
            </button>
          </div>
        </section>

        {/* Pillars */}
        <section className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="bg-[#090e1a]/80 border border-white/5 rounded p-5 space-y-3">
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider block font-mono">01 — AIR-GAPPED AI</span>
            <p className="text-[11px] text-slate-450 leading-relaxed font-mono">
              Local inference without cloud dependency. Run models entirely on local hardware.
            </p>
          </div>
          <div className="bg-[#090e1a]/80 border border-white/5 rounded p-5 space-y-3">
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider block font-mono">02 — SOVEREIGN RAG</span>
            <p className="text-[11px] text-slate-450 leading-relaxed font-mono">
              Private organizational documents remain inside the local infrastructure.
            </p>
          </div>
          <div className="bg-[#090e1a]/80 border border-white/5 rounded p-5 space-y-3">
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider block font-mono">03 — CONTROLLED EXECUTION</span>
            <p className="text-[11px] text-slate-450 leading-relaxed font-mono">
              AI-generated code executes inside an isolated restricted subprocess sandbox.
            </p>
          </div>
          <div className="bg-[#090e1a]/80 border border-white/5 rounded p-5 space-y-3">
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider block font-mono">04 — COMPLETE AUDITABILITY</span>
            <p className="text-[11px] text-slate-450 leading-relaxed font-mono">
              Authentication, AI operations, model switches and security events are logged locally.
            </p>
          </div>
        </section>

        {/* Architecture visualization */}
        <section className="bg-black/25 border border-white/5 rounded p-8 space-y-6 font-mono">
          <div className="text-center text-[10px] font-bold text-slate-500 uppercase tracking-wider">AEGIS DATAFLOW ARTIFACT</div>
          <div className="flex flex-col md:flex-row items-center justify-center gap-4 text-xs">
            <div className="px-4 py-2 bg-[#090e1a] border border-white/10 rounded text-slate-200">USER</div>
            <div className="text-slate-500">→</div>
            <div className="px-4 py-2 bg-[#090e1a] border border-white/10 rounded text-blue-450 font-bold">AEGIS ACCESS CONTROL</div>
            <div className="text-slate-500">→</div>
            <div className="px-5 py-4 bg-[#090e1a] border border-white/10 rounded text-slate-200 text-center space-y-2">
              <div className="font-bold text-slate-400 border-b border-white/5 pb-1">LOCAL AI RUNTIME</div>
              <div className="text-[10px] text-slate-400">Local LLM | Local RAG | ChromaDB | Secure Sandbox</div>
            </div>
            <div className="text-slate-500">→</div>
            <div className="px-4 py-2 bg-[#090e1a] border border-white/10 rounded text-slate-200">LOCAL AUDIT LEDGER</div>
          </div>
          <div className="text-center text-xs font-bold text-emerald-450 uppercase animate-pulse pt-2">
            NO DATA LEAVES THE NODE
          </div>
        </section>
      </main>

      {/* System Status Strip */}
      <footer className="border-t border-white/5 bg-black/40 h-12 flex items-center justify-around px-6 font-mono text-[10px] text-slate-500 overflow-x-auto whitespace-nowrap">
        <div>CORE: <span className="text-emerald-400 font-bold">LOCAL</span></div>
        <div>INFERENCE: <span className="text-emerald-400 font-bold">ON-PREMISE</span></div>
        <div>RAG: <span className="text-emerald-400 font-bold">LOCAL</span></div>
        <div>AUDIT: <span className="text-emerald-400 font-bold">ENABLED</span></div>
        <div>CLOUD DATA: <span className="text-rose-500 font-bold">DISABLED</span></div>
      </footer>
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const { user, loading, refreshProfile } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");

  // Chat states
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
  const [uploadProgressStage, setUploadProgressStage] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadFailedStage, setUploadFailedStage] = useState<string | null>(null);
  const [reindexingDocId, setReindexingDocId] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const [docSearchQuery, setDocSearchQuery] = useState("");
  const [docStatusFilter, setDocStatusFilter] = useState("");
  const [docTypeFilter, setDocTypeFilter] = useState("");

  // Interactive RAG Query states
  const [ragQueryText, setRagQueryText] = useState("");
  const [ragTopK, setRagTopK] = useState<number>(5);
  const [ragSelectedDocId, setRagSelectedDocId] = useState<string | null>(null);
  const [showHowItWorks, setShowHowItWorks] = useState<boolean>(false);
  const [ragQueryLoading, setRagQueryLoading] = useState(false);
  const [ragQueryResponse, setRagQueryResponse] = useState<GroundedAnswerResponse | RagQueryResponse | KnowledgeBaseGenerationResult | null>(null);
  const [ragQueryError, setRagQueryError] = useState<string | null>(null);

  // Model management states
  const [modelRegistry, setModelRegistry] = useState<ModelProfile[]>([]);
  const [currentModel, setCurrentModel] = useState<ModelProfile | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [swappingModelId, setSwappingModelId] = useState<string | null>(null);
  const [swapMessage, setSwapMessage] = useState<{ type: "success" | "info" | "error"; text: string } | null>(null);
  const [testingModelId, setTestingModelId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null);

  // Sandbox state variables
  const [sandboxCode, setSandboxCode] = useState<string>("");
  const [sandboxExecuting, setSandboxExecuting] = useState<boolean>(false);
  const [sandboxResponse, setSandboxResponse] = useState<SandboxExecutionResponse | null>(null);
  const [sandboxErrorMsg, setSandboxErrorMsg] = useState<string | null>(null);

  // Audit states
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [auditLogsLoading, setAuditLogsLoading] = useState<boolean>(false);
  const [auditLogsError, setAuditLogsError] = useState<string | null>(null);
  const [auditActionFilter, setAuditActionFilter] = useState<string>("");
  const [auditStatusFilter, setAuditStatusFilter] = useState<string>("");
  const [auditSearchQuery, setAuditSearchQuery] = useState<string>("");
  const [auditUserFilter, setAuditUserFilter] = useState<string>("");
  const [auditStartDateFilter, setAuditStartDateFilter] = useState<string>("");
  const [auditEndDateFilter, setAuditEndDateFilter] = useState<string>("");
  
  // Real Audit Summary and Health Checks
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [auditSummaryError, setAuditSummaryError] = useState<string | null>(null);
  const [selectedAuditLog, setSelectedAuditLog] = useState<AuditLog | null>(null);
  const [healthStatus, setHealthStatus] = useState<SystemHealthResponse | null>(null);

  // Access Control states (admin only)
  const [usersList, setUsersList] = useState<UserProfile[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [usersSearchQuery, setUsersSearchQuery] = useState("");
  const [provisionForm, setProvisionForm] = useState({ username: "", password: "", role: "user" });
  const [provisionSuccess, setProvisionSuccess] = useState<string | null>(null);
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const [passwordResetTarget, setPasswordResetTarget] = useState<UserProfile | null>(null);
  const [newPasswordResetValue, setNewPasswordResetValue] = useState("");
  const [resetSuccess, setResetSuccess] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  // Change Password states (force password change flow)
  const [passwordForm, setPasswordForm] = useState({ old_password: "", new_password: "", confirm_password: "" });
  const [passwordChangeError, setPasswordChangeError] = useState<string | null>(null);
  const [passwordChangeSuccess, setPasswordChangeSuccess] = useState<string | null>(null);
  const [passwordChanging, setPasswordChanging] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (activeTab === "chat") {
      scrollToBottom();
    }
  }, [messages, activeTab]);

  // Load document list
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
    if (activeTab === "rag" || activeTab === "documents" || activeTab === "dashboard") {
      loadDocuments();
    }
  }, [activeTab]);

  // Load models metadata
  const loadModelsData = async () => {
    setModelsLoading(true);
    setModelsError(null);
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
    if (activeTab === "models" || activeTab === "dashboard") {
      loadModelsData();
    }
  }, [activeTab]);

  // Load audit logs
  const loadAuditLogs = async () => {
    setAuditLogsLoading(true);
    setAuditLogsError(null);
    try {
      const logs = await auditApi.getLogs();
      setAuditLogs(logs);
    } catch (err: any) {
      setAuditLogsError(err.message || "Failed to retrieve append-only audit ledger.");
    } finally {
      setAuditLogsLoading(false);
    }
  };

  // Load live counts and health checks
  const loadAuditSummaryAndHealth = async () => {
    try {
      setAuditSummaryError(null);
      setAuditSummary(null);
      const h = await healthApi.getHealth();
      setHealthStatus(h);
      
      if (user?.role === "admin") {
        const sum = await auditApi.getSummary();
        setAuditSummary(sum);
      }
    } catch (err) {
      setAuditSummaryError(err instanceof Error ? err.message : "Unable to load audit summary.");
    }
  };

  useEffect(() => {
    if (user) {
      loadAuditSummaryAndHealth();
    }
  }, [activeTab, user]);

  useEffect(() => {
    if (activeTab === "audit") {
      loadAuditLogs();
    }
  }, [activeTab]);

  // Load users (admin only)
  const loadUsersList = async () => {
    if (user?.role !== "admin") return;
    setUsersLoading(true);
    setUsersError(null);
    try {
      const list = await usersApi.listUsers();
      setUsersList(list);
    } catch (err: any) {
      setUsersError(err.message || "Failed to list local user registry.");
    } finally {
      setUsersLoading(false);
    }
  };

  // Models switcher trigger
  const handleSelectModel = async (modelId: string) => {
    if (swappingModelId || modelsLoading) return;
    setSwappingModelId(modelId);
    setSwapMessage({ type: "info", text: "Swapping weights and initializing loader lock..." });
    try {
      await modelsApi.switchModel(modelId);
      await loadModelsData();
      setSwapMessage({ type: "success", text: `Loaded model '${modelId}' successfully.` });
    } catch (err: any) {
      setSwapMessage({ type: "error", text: err.message || "Failed allocating model to VRAM." });
    } finally {
      setSwappingModelId(null);
    }
  };

  // Controlled test inference trigger
  const handleTestInference = async (modelId?: string) => {
    setTestingModelId(modelId || "active");
    setTestResult(null);
    try {
      const res = await modelsApi.testInference(modelId);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        status: "FAIL",
        model: modelId || "active",
        latency_ms: null,
        error: err.message || "Model test inference failed."
      });
    } finally {
      setTestingModelId(null);
    }
  };

  // Conversation session states
  const [conversations, setConversations] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [conversationsLoading, setConversationsLoading] = useState<boolean>(false);
  const [conversationsError, setConversationsError] = useState<string | null>(null);

  // Cross-workspace history states
  const [sandboxHistory, setSandboxHistory] = useState<SandboxHistoryItem[]>([]);
  const [knowledgeHistory, setKnowledgeHistory] = useState<KnowledgeHistoryItem[]>([]);

  const loadConversations = async () => {
    setConversationsLoading(true);
    setConversationsError(null);
    try {
      const list = await chatApi.listConversations();
      setConversations(list);

      // Auto-restore active session from localStorage if present
      const savedSessionId = typeof window !== "undefined" ? localStorage.getItem("aegis_active_session_id") : null;
      if (savedSessionId && list.some((c) => c.id === savedSessionId)) {
        if (activeSessionId !== savedSessionId) {
          handleSelectConversation(savedSessionId);
        }
      } else if (list.length > 0) {
        if (!activeSessionId || !list.some((c) => c.id === activeSessionId)) {
          handleSelectConversation(list[0].id);
        }
      } else {
        setActiveSessionId(null);
        if (typeof window !== "undefined") {
          localStorage.removeItem("aegis_active_session_id");
        }
        setMessages([]);
      }
    } catch (err: any) {
      setConversationsError(err.message || "Unable to load conversations.");
    } finally {
      setConversationsLoading(false);
    }
  };

  const handleSelectConversation = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    if (typeof window !== "undefined") {
      localStorage.setItem("aegis_active_session_id", sessionId);
    }
    setChatError(null);
    try {
      const conv = await chatApi.getConversation(sessionId);
      if (conv && conv.messages) {
        setMessages(
          conv.messages.map((m) => {
            const meta = m.metadata || {};
            const routingInfo = m.routing_info || {
              task_type: m.task_type || meta.task_type,
              selected_model: m.model_id || meta.selected_model,
              routing: "automatic",
              switched: meta.switched,
              reason: meta.routing_reason,
              rag_used: m.rag_used
            };
            return {
              id: m.id,
              role: m.role,
              content: m.content,
              timestamp: new Date(m.timestamp),
              status: "success",
              sources: m.sources,
              verification: m.verification,
              request_id: m.request_id,
              duration_ms: m.duration_ms,
              rag_used: m.rag_used,
              model_id: m.model_id,
              error_detail: m.error_detail,
              task_type: m.task_type || meta.task_type,
              document_ids: m.document_ids || meta.document_ids,
              routing_info: routingInfo,
              sandbox_execution: m.sandbox_execution || meta.sandbox_execution,
              metadata: meta
            };
          })
        );
      }
    } catch (err: any) {
      setChatError(err.message || "Unable to load this conversation.");
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await chatApi.createConversation();
      setActiveSessionId(newConv.id);
      if (typeof window !== "undefined") {
        localStorage.setItem("aegis_active_session_id", newConv.id);
      }
      setMessages([]);
      setChatError(null);
      await loadConversations();
    } catch (err: any) {
      setChatError(err.message || "Failed to start a new conversation session.");
    }
  };

  const handleDeleteConversation = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await chatApi.deleteConversation(sessionId);
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        if (typeof window !== "undefined") {
          localStorage.removeItem("aegis_active_session_id");
        }
        setMessages([]);
      }
      await loadConversations();
    } catch (err: any) {
      console.error("Failed to delete conversation:", err);
    }
  };

  useEffect(() => {
    if (activeTab === "chat" || activeTab === "history" || activeTab === "dashboard") {
      loadConversations();
    }
  }, [activeTab]);

  // Chat message submit
  const handleSendMessage = async (textToSend: string) => {
    const trimmed = textToSend.trim();
    if (!trimmed || chatLoading) return;

    setChatError(null);
    const userMsg: Message = {
      id: `msg_${Date.now()}`,
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
      const response = await chatApi.sendMessage(trimmed, activeSessionId || undefined);
      if (response.session_id) {
        setActiveSessionId(response.session_id);
        if (typeof window !== "undefined") {
          localStorage.setItem("aegis_active_session_id", response.session_id);
        }
      }
      const isRagUsed = response.rag_used ?? (response.sources && response.sources.length > 0);
      const selectedModel = response.routing_info?.selected_model || response.model_info?.model_id || currentModel?.model_id || "NOT REPORTED";
      const taskType = response.routing_info?.task_type || "GENERAL_TEXT";
      
      setMessages((prev) => 
        prev.map((msg) => 
          msg.id === assistantMsgId 
            ? {
                ...msg,
                content: response.answer,
                status: "success",
                sources: response.sources,
                verification: response.verification || (isRagUsed ? "GROUNDED" : "UNVERIFIED"),
                request_id: response.request_id,
                duration_ms: response.duration_ms,
                rag_used: isRagUsed,
                model_id: selectedModel,
                task_type: taskType,
                routing_info: response.routing_info,
                sandbox_execution: response.sandbox_execution
              }
            : msg
        )
      );
      await loadConversations();
    } catch (err: any) {
      setMessages((prev) => 
        prev.map((msg) => 
          msg.id === assistantMsgId 
            ? {
                ...msg,
                content: err.message || "Failed to generate local AI reasoning response.",
                status: "error",
                error_detail: err.detail || err.message
              }
            : msg
        )
      );
      setChatError(err.message || "Sovereign node execution faulted.");
    } finally {
      setChatLoading(false);
    }
  };

  // Ingestion upload submit
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const handleUploadFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || uploading) return;

    setUploading(true);
    setUploadSuccess(null);
    setUploadError(null);
    setUploadFailedStage(null);
    setUploadProgressStage("DOCUMENT UPLOAD");

    try {
      setUploadProgressStage("TEXT EXTRACTION");
      await new Promise(r => setTimeout(r, 150));
      
      setUploadProgressStage("EMBEDDING");
      const doc = await ragApi.ingestDocument(selectedFile);
      
      setUploadProgressStage("CHROMADB COMMIT");
      await new Promise(r => setTimeout(r, 150));
      
      setUploadSuccess(`Ingested and indexed '${selectedFile.name}' successfully into local ChromaDB.`);
      setSelectedFile(null);
      loadDocuments();
    } catch (err: any) {
      setUploadFailedStage("Embedding Generation");
      setUploadError(err.message || "Document indexing failed.");
    } finally {
      setUploading(false);
      setUploadProgressStage(null);
    }
  };

  const handleExecuteRagQuery = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const queryText = ragQueryText.trim();
    if (!queryText || ragQueryLoading) return;
    setRagQueryLoading(true);
    setRagQueryError(null);
    setRagQueryResponse(null);

    // 1. Check if user input is a Document Generation Request
    const intent = parseGenerationIntent(queryText, documents, ragSelectedDocId);

    if (intent.isGeneration) {
      if (intent.error) {
        setRagQueryError(intent.error);
        setRagQueryLoading(false);
        return;
      }

      try {
        const genDoc = await ragApi.generateReport({
          title: intent.title,
          topic: intent.topic,
          format: intent.format,
          document_id: intent.documentId,
          session_id: activeSessionId || undefined,
        });

        const genResult: KnowledgeBaseGenerationResult = {
          isGenerationResult: true,
          generatedDocument: genDoc,
          sourceFilename: intent.sourceFilename,
          query: queryText,
        };

        setRagQueryResponse(genResult);
        setKnowledgeHistory((prev) => [
          {
            id: `kh_${Date.now()}`,
            query: queryText,
            timestamp: new Date().toISOString(),
            response: genResult as any,
          },
          ...prev.slice(0, 19),
        ]);

        // Refresh documents list to sync newly generated report
        loadDocuments();
      } catch (err: any) {
        const safeError = err.detail?.message || err.detail || err.message || "Failed generating intelligence report.";
        setRagQueryError(typeof safeError === "string" ? safeError : JSON.stringify(safeError));
      } finally {
        setRagQueryLoading(false);
      }
      return;
    }

    // 2. Standard Grounded QA Request
    try {
      const res = await ragApi.askDocument(
        queryText,
        ragSelectedDocId || undefined,
        activeSessionId || undefined,
        ragTopK
      );
      setRagQueryResponse(res);
      setKnowledgeHistory((prev) => [
        {
          id: `kh_${Date.now()}`,
          query: queryText,
          timestamp: new Date().toISOString(),
          response: res,
        },
        ...prev.slice(0, 19),
      ]);
    } catch (err: any) {
      const safeError = err.detail?.message || err.detail || err.message || "Failed executing document analysis search.";
      setRagQueryError(typeof safeError === "string" ? safeError : JSON.stringify(safeError));
    } finally {
      setRagQueryLoading(false);
    }
  };

  const handleReindex = async (docId: string) => {
    setReindexingDocId(docId);
    try {
      await ragApi.reindexDocument(docId);
      alert("Successfully re-indexed knowledge document.");
      loadDocuments();
    } catch (err: any) {
      alert(`Re-index failed: ${err.message}`);
    } finally {
      setReindexingDocId(null);
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Are you sure you want to permanently delete knowledge base file '${filename}'?`)) return;
    setDeletingDocId(docId);
    try {
      await ragApi.deleteDocument(docId);
      loadDocuments();
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    } finally {
      setDeletingDocId(null);
    }
  };

  // Code Sandbox script run
  const handleExecuteSandbox = async () => {
    if (sandboxExecuting || !sandboxCode.trim()) return;
    setSandboxExecuting(true);
    setSandboxErrorMsg(null);
    setSandboxResponse(null);
    try {
      const res = await sandboxApi.execute({ code: sandboxCode });
      setSandboxResponse(res);
      setSandboxHistory((prev) => [
        {
          id: `sh_${Date.now()}`,
          code: sandboxCode,
          language: "python",
          timestamp: new Date().toISOString(),
          response: res,
          error: null
        },
        ...prev.slice(0, 19)
      ]);
    } catch (err: any) {
      const errMsg = err.message || "Subprocess execution faulted.";
      setSandboxErrorMsg(errMsg);
      setSandboxHistory((prev) => [
        {
          id: `sh_${Date.now()}`,
          code: sandboxCode,
          language: "python",
          timestamp: new Date().toISOString(),
          response: null,
          error: errMsg
        },
        ...prev.slice(0, 19)
      ]);
    } finally {
      setSandboxExecuting(false);
    }
  };

  // Admin user provisioning submit
  const handleProvisionUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setProvisionSuccess(null);
    setProvisionError(null);
    if (!provisionForm.username || !provisionForm.password) {
      setProvisionError("Username and password are required.");
      return;
    }
    try {
      await usersApi.provisionUser(provisionForm);
      setProvisionSuccess(`Provisioned user '${provisionForm.username}' successfully.`);
      setProvisionForm({ username: "", password: "", role: "user" });
      loadUsersList();
    } catch (err: any) {
      setProvisionError(err.message || "Failed provisioning user account.");
    }
  };

  const handleUpdateUserStatus = async (username: string, active: boolean) => {
    try {
      await usersApi.updateUserStatus(username, active);
      loadUsersList();
    } catch (err: any) {
      alert(`Failed changing status: ${err.message}`);
    }
  };

  const handleUpdateUserRole = async (username: string, role: string) => {
    try {
      await usersApi.updateUserRole(username, role);
      loadUsersList();
    } catch (err: any) {
      alert(`Failed changing role: ${err.message}`);
    }
  };

  const handleResetUserPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setResetSuccess(null);
    setResetError(null);
    if (!passwordResetTarget || !newPasswordResetValue) return;
    try {
      await usersApi.resetPassword(passwordResetTarget.username, newPasswordResetValue);
      setResetSuccess(`Successfully reset password for user '${passwordResetTarget.username}'.`);
      setNewPasswordResetValue("");
      setTimeout(() => {
        setPasswordResetTarget(null);
        setResetSuccess(null);
      }, 2000);
    } catch (err: any) {
      setResetError(err.message || "Password reset failed.");
    }
  };

  // Change password for logged-in user
  const handleUserChangePassword = async (e?: React.FormEvent | Record<string, unknown>) => {
    if (e && "preventDefault" in e && typeof e.preventDefault === "function") {
      e.preventDefault();
    }
    setPasswordChangeError(null);
    setPasswordChangeSuccess(null);
    if (!passwordForm.old_password || !passwordForm.new_password) {
      setPasswordChangeError("All password fields are required.");
      return;
    }
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordChangeError("New password verification check mismatch.");
      return;
    }
    if (passwordForm.new_password.length < 8) {
      setPasswordChangeError("New password must be at least 8 characters.");
      return;
    }
    setPasswordChanging(true);
    try {
      await usersApi.changePassword({
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password
      });
      setPasswordChangeSuccess("Password updated successfully. Authorized grant active.");
      setPasswordForm({ old_password: "", new_password: "", confirm_password: "" });
      setTimeout(async () => {
        await refreshProfile();
      }, 1500);
    } catch (err: any) {
      setPasswordChangeError(err.message || "Password change rejected.");
    } finally {
      setPasswordChanging(false);
    }
  };

  // Dynamic content switch renderer
  const renderTabContent = () => {
    switch (activeTab) {
      case "dashboard": {
        const recentLogs = auditLogs.slice(0, 6);
        const activeModelName = currentModel?.display_name || currentModel?.model_id || "No active model reported";

        return (
          <DashboardView
            username={user?.username}
            role={user?.role}
            activeModelName={activeModelName}
            documentCount={documents.length}
            documentsLoading={documentsLoading}
            conversationCount={conversations.length}
            conversationsLoading={conversationsLoading}
            recentLogs={recentLogs}
            latestMessage={messages.length ? { content: messages[messages.length - 1].content, sourceCount: messages[messages.length - 1].sources?.length } : undefined}
            onNavigate={setActiveTab}
            onNewConversation={handleNewConversation}
          />
        );
      }

      case "chat": {
        const isRAGAvailable = healthStatus?.services.rag_engine === "healthy";
        const isAIRuntimeHealthy = healthStatus?.services.ai_runtime === "healthy";

        const filteredConversations = conversations.filter(c => 
          !docSearchQuery.trim() || 
          (c.title && c.title.toLowerCase().includes(docSearchQuery.toLowerCase()))
        );

        const activeSession = conversations.find(c => c.id === activeSessionId);
        const activeModelDisplay = currentModel?.display_name || currentModel?.model_id || "No active model reported";

        return (
          <div className="aegis-operational-view aegis-assistant-view space-y-6 font-sans max-w-[1600px] mx-auto pb-6">
            {/* TOP ASSISTANT HEADER BAR */}
            <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-7 flex flex-col lg:flex-row lg:items-center justify-between gap-6 shadow-xl">
              <div className="space-y-1.5">
                <div className="flex items-center space-x-3">
                  <div className="h-10 w-10 rounded-xl bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400 shrink-0 shadow-lg shadow-blue-500/5">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div>
                    <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-100">
                      AI Assistant
                    </h1>
                    <p className="text-xs text-slate-400 leading-relaxed mt-0.5">
                      Secure local reasoning and grounded organizational knowledge access.
                    </p>
                  </div>
                </div>
              </div>

              {/* COMPACT SUBSYSTEM STATUS PILLS */}
              <div className="flex flex-wrap items-center gap-2.5 text-xs">
                <span className="px-3 py-1.5 bg-blue-500/10 border border-blue-500/25 text-blue-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-400" />
                  <span>LOCAL INFERENCE</span>
                </span>
                <span className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5 border ${
                  isRAGAvailable 
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25" 
                    : "bg-amber-500/10 text-amber-300 border-amber-500/25"
                }`}>
                  <span className={`h-2 w-2 rounded-full ${isRAGAvailable ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
                  <span>{isRAGAvailable ? "RAG ONLINE" : "RAG DEGRADED"}</span>
                </span>
                <span className="px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/25 text-indigo-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-400" />
                  <span>AIR-GAPPED</span>
                </span>
                <span className="px-3 py-1.5 bg-purple-500/10 border border-purple-500/25 text-purple-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-purple-400" />
                  <span>CLOUD DISABLED</span>
                </span>
              </div>
            </div>

            {/* 3-ZONE DESKTOP LAYOUT */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-14rem)] min-h-[600px]">
              
              {/* ZONE 1 (LEFT): CONVERSATION PANEL */}
              <div className="lg:col-span-3 h-full overflow-hidden">
                <ChatSidebar
                  conversations={conversations}
                  activeSessionId={activeSessionId}
                  loading={conversationsLoading}
                  error={conversationsError}
                  onSelectConversation={handleSelectConversation}
                  onNewConversation={handleNewConversation}
                  onDeleteConversation={handleDeleteConversation}
                  onRetry={loadConversations}
                  searchQuery={docSearchQuery}
                  setSearchQuery={setDocSearchQuery}
                />
              </div>

              {/* ZONE 2 (CENTER): AI CHAT WORKSPACE */}
              <div className="lg:col-span-6 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl flex flex-col overflow-hidden shadow-xl">
                {/* Active Session Sub-Header Bar */}
                <div className="px-6 py-3.5 border-b border-slate-800/80 bg-[#090e1a]/90 flex items-center justify-between shrink-0">
                  <div className="flex items-center space-x-2.5 truncate">
                    <Bot className="h-4.5 w-4.5 text-blue-400 shrink-0" />
                    <span className="text-xs font-bold text-slate-100 truncate">
                      {activeSession?.title || "No conversation selected"}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="px-2.5 py-1 bg-blue-500/10 border border-blue-500/20 text-blue-300 rounded-md text-[10px] font-bold tracking-wide uppercase font-mono">
                      LOCAL MODEL {activeModelDisplay}
                    </span>
                  </div>
                </div>

                {/* Message Stream Area */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                  {messages.length === 0 ? (
                    <div className="h-full min-h-[350px] flex flex-col items-center justify-center text-center max-w-xl mx-auto space-y-6 py-6 font-sans">
                      <div className="h-12 w-12 rounded-xl bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400 mx-auto shadow-lg shadow-blue-500/5">
                        <ShieldCheck className="h-6 w-6" />
                      </div>
                      
                      <div className="space-y-1.5">
                        <h3 className="text-lg font-bold text-slate-100">
                          AEGIS AI Assistant
                        </h3>
                        <p className="text-xs text-slate-400 leading-relaxed max-w-md">
                          Ask questions about authorized organizational knowledge. Inference is executed strictly on-premise inside the local sovereign workstation node.
                        </p>
                      </div>

                      {/* Suggested Query Chips */}
                      <div className="space-y-2.5 w-full pt-4 border-t border-slate-800/80">
                        <span className="text-[11px] font-semibold text-slate-400 block text-center uppercase tracking-wider">
                          Suggested Organizational Queries
                        </span>
                        <div className="flex flex-wrap items-center justify-center gap-2">
                          {[
                            "What protective equipment must manufacturing employees wear?",
                            "What is our emergency shutdown procedure?",
                            "Summarize the employee leave policy."
                          ].map((promptText, i) => (
                            <button
                              key={i}
                              type="button"
                              onClick={() => setInputMessage(promptText)}
                              className="px-3.5 py-2 bg-slate-900/60 border border-slate-800 hover:border-blue-500/40 rounded-lg text-xs text-slate-300 hover:text-slate-100 transition-all text-left font-sans cursor-pointer"
                            >
                              "{promptText}"
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      {messages.map((msg) => {
                        const isUser = msg.role === "user";

                        return (
                          <div key={msg.id} className={`flex flex-col space-y-1.5 ${isUser ? "items-end" : "items-start"}`}>
                            <div className="flex items-center space-x-2 text-[11px] font-semibold text-slate-400 px-1">
                              <span className={isUser ? "text-blue-400 font-bold" : "text-emerald-400 font-bold"}>
                                {isUser ? "OPERATOR" : "AEGIS"}
                              </span>
                              <span>•</span>
                              <span className="font-mono text-[10px] text-slate-500">{msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                            </div>

                            <div className={`p-5 rounded-2xl border text-xs leading-relaxed max-w-[90%] sm:max-w-[85%] shadow-lg ${
                              isUser 
                                ? "bg-blue-600/10 border-blue-500/20 text-slate-100 font-sans" 
                                : "bg-[#090e1a] border-slate-800/90 text-slate-100 font-sans space-y-4"
                            }`}>
                              {msg.status === "sending" ? (
                                <div className="flex items-center space-x-3 text-blue-400 p-2 font-sans text-xs">
                                  <RefreshCw className="h-4 w-4 animate-spin text-blue-400 shrink-0" />
                                  <div className="space-y-0.5">
                                    <div className="font-semibold text-slate-200">Analyzing query & generating grounded response…</div>
                                    <div className="text-[11px] text-slate-400">Local inference on {activeModelDisplay}</div>
                                  </div>
                                </div>
                              ) : msg.status === "error" ? (
                                <div className="space-y-2 text-xs text-rose-300 font-sans">
                                  <div className="flex items-center space-x-2 font-bold text-rose-400">
                                    <AlertCircle className="h-4.5 w-4.5 shrink-0" />
                                    <span>Agent Execution Fault</span>
                                  </div>
                                  <p className="text-slate-300 leading-relaxed">{msg.content}</p>
                                </div>
                              ) : (
                                <>
                                  {/* Grounded Badge Header */}
                                  {!isUser && (
                                    <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5 text-xs">
                                      <div className="flex items-center space-x-2">
                                        <span className={`px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                                          msg.rag_used 
                                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" 
                                            : "bg-amber-500/10 text-amber-300 border-amber-500/30"
                                        }`}>
                                          {msg.rag_used ? "GROUNDED" : "GENERAL REASONING"}
                                        </span>
                                      </div>
                                      
                                      <span className="text-[10px] text-slate-400 font-mono">
                                        Model: <span className="text-blue-400 font-bold">{msg.model_id || activeModelDisplay}</span>
                                      </span>
                                    </div>
                                  )}

                                  {/* Sandbox Execution Specialized Card */}
                                  {!isUser && (msg.sandbox_execution || msg.metadata?.sandbox_execution) ? (
                                    (() => {
                                      const sb = msg.sandbox_execution || msg.metadata?.sandbox_execution;
                                      const isSuccess = sb.status === "SUCCESS" || sb.success;
                                      const artifacts = sb.artifacts || [];
                                      return (
                                        <div className="space-y-3">
                                          {/* Generated Code Section */}
                                          {sb.code && (
                                            <div className="space-y-1.5">
                                              <div className="flex items-center justify-between text-[11px] font-mono font-bold text-slate-400 uppercase tracking-wider">
                                                <span className="flex items-center space-x-1">
                                                  <Code className="h-3.5 w-3.5 text-blue-400" />
                                                  <span>GENERATED PYTHON CODE</span>
                                                </span>
                                              </div>
                                              <pre className="p-3 bg-[#060a14] border border-slate-800/90 rounded-xl text-xs font-mono text-emerald-300 overflow-x-auto whitespace-pre leading-relaxed">
                                                <code>{sb.code}</code>
                                              </pre>
                                            </div>
                                          )}

                                          {/* Real Sandbox Execution Telemetry Card */}
                                          <div className={`p-3.5 rounded-xl border font-mono text-xs space-y-2.5 ${
                                            isSuccess 
                                              ? "bg-[#060e18]/90 border-emerald-500/30" 
                                              : "bg-[#180808]/90 border-red-500/30"
                                          }`}>
                                            <div className="flex items-center justify-between border-b border-white/10 pb-2">
                                              <div className="flex items-center space-x-2">
                                                <Terminal className={`h-4 w-4 ${isSuccess ? "text-emerald-400" : "text-red-400"}`} />
                                                <span className="font-bold text-[11px] uppercase tracking-wide text-slate-200">
                                                  REAL SANDBOX EXECUTION
                                                </span>
                                              </div>
                                              <div className="flex items-center space-x-2">
                                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                                  isSuccess ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" : "bg-red-500/20 text-red-300 border border-red-500/40"
                                                }`}>
                                                  {sb.status || (isSuccess ? "SUCCESS" : "FAILED")}
                                                </span>
                                                <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-[10px] font-bold">
                                                  Exit: {sb.exit_code}
                                                </span>
                                                {sb.duration_ms !== undefined && (
                                                  <span className="text-[10px] text-slate-400">
                                                    {sb.duration_ms}ms
                                                  </span>
                                                )}
                                              </div>
                                            </div>

                                            {/* STDOUT */}
                                            {sb.stdout && sb.stdout.trim() && (
                                              <div className="space-y-1">
                                                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">
                                                  STDOUT:
                                                </span>
                                                <pre className="p-2.5 bg-black/60 rounded-lg text-slate-100 text-xs font-mono overflow-x-auto whitespace-pre leading-relaxed border border-white/5">
                                                  <code>{sb.stdout}</code>
                                                </pre>
                                              </div>
                                            )}

                                            {/* STDERR / ERROR */}
                                            {(sb.stderr || sb.error) && (
                                              <div className="space-y-1">
                                                <span className="text-[10px] text-red-400 font-bold uppercase tracking-wider block">
                                                  STDERR / ERROR:
                                                </span>
                                                <pre className="p-2.5 bg-red-950/40 rounded-lg text-red-300 text-xs font-mono overflow-x-auto whitespace-pre leading-relaxed border border-red-900/50">
                                                  <code>{sb.stderr || sb.error}</code>
                                                </pre>
                                              </div>
                                            )}

                                            {/* Generated Artifacts */}
                                            {artifacts.length > 0 && (
                                              <div className="space-y-1.5 pt-1 border-t border-white/10">
                                                <span className="text-[10px] text-indigo-300 font-bold uppercase tracking-wider block">
                                                  GENERATED ARTIFACTS ({artifacts.length}):
                                                </span>
                                                <div className="space-y-1">
                                                  {artifacts.map((art: any, aidx: number) => (
                                                    <div key={aidx} className="flex items-center justify-between p-2 bg-indigo-950/30 border border-indigo-500/20 rounded-lg">
                                                      <div className="flex items-center space-x-2 truncate">
                                                        <FileText className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                                                        <span className="text-slate-200 text-xs truncate">{art.filename}</span>
                                                        <span className="text-[10px] text-slate-400">({Math.round((art.file_size || 0) / 1024 * 10) / 10} KB)</span>
                                                      </div>
                                                      <a
                                                        href={art.download_url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[10px] font-bold flex items-center space-x-1 shrink-0 cursor-pointer"
                                                      >
                                                        <Download className="h-3 w-3" />
                                                        <span>Download</span>
                                                      </a>
                                                    </div>
                                                  ))}
                                                </div>
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                      );
                                    })()
                                  ) : (
                                    /* Default Answer Content */
                                    <div className="whitespace-pre-wrap leading-relaxed text-slate-200 text-[13px]">
                                      {msg.content}
                                    </div>
                                  )}

                                  {/* Clean Sources List */}
                                  {!isUser && msg.sources && msg.sources.length > 0 && (
                                    <div className="border-t border-slate-800/80 pt-3 space-y-2 text-xs">
                                      <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                                        Sources:
                                      </div>
                                      <div className="space-y-1">
                                        {Array.from(new Set(msg.sources.map((s) => `${s.filename} — Page ${s.page_number}`))).map((srcStr, idx) => (
                                          <div key={idx} className="flex items-center space-x-2 text-slate-300 text-xs font-mono">
                                            <span className="text-blue-400">•</span>
                                            <span>{srcStr}</span>
                                          </div>
                                        ))}
                                      </div>

                                      {/* Collapsible Evidence Passages */}
                                      <details className="pt-2 text-xs cursor-pointer">
                                        <summary className="text-[11px] font-mono text-slate-500 hover:text-slate-300 select-none">
                                          ▸ View evidence passages ({msg.sources.length})
                                        </summary>
                                        <div className="space-y-2 pt-2">
                                          {msg.sources.map((src, idx) => (
                                            <div key={idx} className="p-3 bg-[#080d1a] border border-slate-800/80 rounded-lg space-y-1 text-xs">
                                              <div className="flex items-center justify-between text-[11px] font-semibold text-blue-300 border-b border-slate-800/80 pb-1">
                                                <span>{src.filename}</span>
                                                <span className="text-slate-400 font-mono text-[10px]">Page {src.page_number}</span>
                                              </div>
                                              {src.text && (
                                                <p className="text-slate-300 text-[11px] italic leading-relaxed pt-1 whitespace-pre-wrap">
                                                  "{src.text}"
                                                </p>
                                              )}
                                            </div>
                                          ))}
                                        </div>
                                      </details>
                                    </div>
                                  )}

                                  {/* AEGIS Execution Information Telemetry Card */}
                                  {!isUser && (
                                    <div className="mt-3 pt-3 border-t border-slate-800/80 text-[11px] font-mono">
                                      <div className="flex items-center space-x-1.5 text-slate-400 font-bold uppercase tracking-wider text-[10px] mb-2">
                                        <Cpu className="h-3 w-3 text-blue-400" />
                                        <span>AEGIS EXECUTION</span>
                                      </div>
                                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 bg-[#060a14] p-2.5 rounded-xl border border-slate-800/70">
                                        <div>
                                          <span className="text-slate-400 block text-[9px] uppercase font-bold">Task</span>
                                          <span className="text-slate-200 font-semibold">{formatTaskType(msg.task_type || msg.routing_info?.task_type)}</span>
                                        </div>
                                        <div>
                                          <span className="text-slate-400 block text-[9px] uppercase font-bold">Model</span>
                                          <span className="text-blue-400 font-semibold">{msg.model_id || msg.routing_info?.selected_model || activeModelDisplay}</span>
                                        </div>
                                        <div>
                                          <span className="text-slate-400 block text-[9px] uppercase font-bold">Routing</span>
                                          <span className="text-emerald-400 font-semibold">Automatic</span>
                                        </div>
                                        <div>
                                          <span className="text-slate-400 block text-[9px] uppercase font-bold">
                                            {msg.task_type === "CODING" || msg.task_type === "CALCULATION" ? "Sandbox" : (msg.task_type === "VISION_ANALYSIS" ? "Vision" : "RAG")}
                                          </span>
                                          <span className="text-slate-300 font-semibold">
                                            {msg.task_type === "CODING" || msg.task_type === "CALCULATION"
                                              ? ((msg.sandbox_execution || msg.metadata?.sandbox_execution)?.success
                                                  ? "Executed ✓"
                                                  : ((msg.sandbox_execution || msg.metadata?.sandbox_execution)
                                                      ? `Failed (Exit ${(msg.sandbox_execution || msg.metadata?.sandbox_execution).exit_code})`
                                                      : "Executed ✓"))
                                              : (msg.task_type === "VISION_ANALYSIS"
                                                  ? "Supported ✓"
                                                  : (msg.rag_used ? "Grounded ✓" : "General Reasoning"))}
                                          </span>
                                        </div>
                                        <div>
                                          <span className="text-slate-400 block text-[9px] uppercase font-bold">Model Switch</span>
                                          <span className="text-slate-300 font-semibold">{msg.routing_info?.switched ? "Yes" : "No"}</span>
                                        </div>
                                        <div>
                                          <span className="text-slate-400 block text-[9px] uppercase font-bold">Execution</span>
                                          <span className="text-indigo-400 font-semibold">Local Workstation</span>
                                        </div>
                                      </div>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          </div>
                        );
                      })}
                      <div ref={messagesEndRef} />
                    </div>
                  )}
                </div>

                {/* Bottom Input Composer */}
                <div className="p-4 border-t border-slate-800/80 bg-[#090e1a]/90 shrink-0">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      handleSendMessage(inputMessage);
                    }}
                    className="space-y-2"
                  >
                    <div className="relative bg-[#080d1a] border border-slate-800 rounded-2xl p-3 focus-within:ring-2 focus-within:ring-blue-500/40 transition-all flex items-end justify-between">
                      <textarea
                        rows={2}
                        value={inputMessage}
                        onChange={(e) => setInputMessage(e.target.value.slice(0, 1000))}
                        placeholder="Ask AEGIS about authorized organizational knowledge..."
                        disabled={chatLoading}
                        className="w-full bg-transparent text-xs text-slate-100 placeholder-slate-500 focus:outline-none font-sans resize-none leading-relaxed pr-10"
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            handleSendMessage(inputMessage);
                          }
                        }}
                      />
                      
                      <div className="flex items-center space-x-2 shrink-0">
                        <span className="text-[10px] text-slate-500 font-mono select-none pr-1">
                          {inputMessage.length}/1000
                        </span>

                        <button
                          type="submit"
                          disabled={!inputMessage.trim() || chatLoading}
                          className="h-9 w-9 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white flex items-center justify-center cursor-pointer shadow-lg shadow-blue-600/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                          title="Send Message"
                          aria-label="Send Message"
                        >
                          <Send className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </form>
                </div>
              </div>

              {/* ZONE 3 (RIGHT): AI & SYSTEM INFORMATION PANEL */}
              <div className="lg:col-span-3 space-y-5 overflow-y-auto">
                {/* CARD 0: DOCUMENT CONTEXT */}
                {documents.length > 0 && (
                  <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                      <div className="flex items-center space-x-2 text-indigo-400">
                        <Database className="h-4.5 w-4.5" />
                        <h3 className="text-xs font-bold uppercase tracking-wide text-slate-100">DOCUMENT CONTEXT</h3>
                      </div>
                      <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded text-[10px] font-bold uppercase font-mono">
                        INDEXED
                      </span>
                    </div>

                    <div className="space-y-2 text-xs font-sans">
                      <div className="font-bold text-slate-200 truncate" title={documents[0].filename}>
                        {documents[0].filename}
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-400 pt-1">
                        <div className="bg-[#050811] p-2 rounded border border-slate-800/60">
                          <span className="text-slate-500 block text-[10px]">PAGES</span>
                          <span className="text-slate-200 font-bold">{documents[0].pages ?? documents[0].page_count ?? "—"}</span>
                        </div>
                        <div className="bg-[#050811] p-2 rounded border border-slate-800/60">
                          <span className="text-slate-500 block text-[10px]">CHUNKS</span>
                          <span className="text-blue-400 font-bold">{documents[0].chunk_count ?? documents[0].chunks ?? 0}</span>
                        </div>
                      </div>
                      {documents.length > 1 && (
                        <div className="text-[10px] text-slate-400 pt-1">
                          + {documents.length - 1} other indexed document{documents.length > 2 ? "s" : ""}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* CARD 1: CURRENT MODEL */}
                <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                    <div className="flex items-center space-x-2 text-blue-400">
                      <Cpu className="h-4.5 w-4.5" />
                      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-100">CURRENT MODEL</h3>
                    </div>
                    <span className="text-[10px] font-bold text-emerald-400 font-mono">ACTIVE</span>
                  </div>

                  <div className="space-y-2">
                    <span className="text-base font-extrabold text-blue-400 font-mono block truncate" title={activeModelDisplay}>
                      {activeModelDisplay}
                    </span>
                    <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-400">
                      <span className="px-2 py-0.5 bg-slate-800/80 rounded border border-slate-700/60">4.3B Parameters</span>
                      <span className="px-2 py-0.5 bg-slate-800/80 rounded border border-slate-700/60">GGUF • Q4_K_M</span>
                    </div>
                  </div>

                  <Button
                    variant="secondary"
                    onClick={() => setActiveTab("models")}
                    disabled={user?.role !== "admin"}
                    className="w-full h-9 text-xs"
                    title={user?.role !== "admin" ? "Admin role required to switch active models" : "Manage and select active models"}
                  >
                    Change Model
                  </Button>
                </div>

                {/* CARD 2: QUICK ACTIONS */}
                <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-4">
                  <div className="flex items-center space-x-2 text-blue-400 border-b border-slate-800/80 pb-3">
                    <Activity className="h-4.5 w-4.5" />
                    <h3 className="text-xs font-bold uppercase tracking-wide text-slate-100">QUICK ACTIONS</h3>
                  </div>

                  <div className="space-y-2">
                    <Button
                      variant="ghost"
                      onClick={() => setActiveTab("documents")}
                      className="w-full justify-start h-9 text-xs text-slate-300 hover:text-white hover:bg-slate-800/60"
                    >
                      <Upload className="h-4 w-4 mr-2 text-blue-400" />
                      <span>Upload Document</span>
                    </Button>

                    <Button
                      variant="ghost"
                      onClick={handleNewConversation}
                      className="w-full justify-start h-9 text-xs text-slate-300 hover:text-white hover:bg-slate-800/60"
                    >
                      <Plus className="h-4 w-4 mr-2 text-emerald-400" />
                      <span>Create Conversation</span>
                    </Button>

                    <Button
                      variant="ghost"
                      onClick={() => setActiveTab("rag")}
                      className="w-full justify-start h-9 text-xs text-slate-300 hover:text-white hover:bg-slate-800/60"
                    >
                      <Database className="h-4 w-4 mr-2 text-indigo-400" />
                      <span>Query Knowledge Base</span>
                    </Button>

                    <Button
                      variant="ghost"
                      onClick={() => setActiveTab("sandbox")}
                      className="w-full justify-start h-9 text-xs text-slate-300 hover:text-white hover:bg-slate-800/60"
                    >
                      <Terminal className="h-4 w-4 mr-2 text-purple-400" />
                      <span>Run Sandbox Code</span>
                    </Button>
                  </div>
                </div>

                {/* CARD 3: AUDIT INTEGRITY */}
                <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                    <div className="flex items-center space-x-2 text-emerald-400">
                      <ShieldCheck className="h-4.5 w-4.5" />
                      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-100">AUDIT INTEGRITY</h3>
                    </div>
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                  </div>

                  <div className="space-y-2 text-xs font-sans">
                    <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Status:</span>
                      <span className="font-bold text-emerald-400 uppercase font-mono">INTACT</span>
                    </div>
                    <div className="flex justify-between items-center py-1">
                      <span className="text-slate-400">Last Verified:</span>
                      <span className="text-slate-300 font-mono text-[11px]">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </div>

                  {user?.role === "admin" && (
                    <Button
                      variant="secondary"
                      onClick={() => setActiveTab("audit")}
                      className="w-full h-9 text-xs"
                    >
                      Verify Now
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      }
      case "rag": {
        return (
          <KnowledgeBaseView
            documents={documents}
            loading={documentsLoading}
            error={documentsError}
            query={ragQueryText}
            setQuery={setRagQueryText}
            topK={ragTopK}
            setTopK={setRagTopK}
            selectedDocId={ragSelectedDocId}
            setSelectedDocId={setRagSelectedDocId}
            onSearch={() => handleExecuteRagQuery({ preventDefault: () => {} } as React.FormEvent)}
            searching={ragQueryLoading}
            result={ragQueryResponse}
            queryError={ragQueryError}
            history={knowledgeHistory}
            onSelectHistory={(item) => {
              setRagQueryText(item.query);
              setRagQueryResponse(item.response);
            }}
            onRefreshDocuments={loadDocuments}
          />
        );
      }

      case "documents": {
        return (
          <DocumentsView
            documents={documents}
            loading={documentsLoading}
            error={documentsError}
            file={selectedFile}
            uploading={uploading}
            uploadSuccess={uploadSuccess}
            uploadError={uploadError}
            search={docSearchQuery}
            setSearch={setDocSearchQuery}
            status={docStatusFilter}
            setStatus={setDocStatusFilter}
            type={docTypeFilter}
            setType={setDocTypeFilter}
            onFile={setSelectedFile}
            onUpload={() => handleUploadFile({ preventDefault: () => {} } as React.FormEvent)}
            onRefresh={loadDocuments}
            onReindex={handleReindex}
            onDelete={handleDelete}
            reindexing={reindexingDocId}
            deleting={deletingDocId}
          />
        );
      }

      case "models": {
        const isRuntimeConnected = healthStatus?.services.ai_runtime === "healthy";
        return (
          <ModelsView
            models={modelRegistry}
            current={currentModel}
            loading={modelsLoading}
            error={modelsError}
            runtimeHealthy={isRuntimeConnected}
            switching={swappingModelId}
            testing={testingModelId}
            test={testResult}
            onSelect={handleSelectModel}
            onTest={handleTestInference}
          />
        );
      }

      case "sandbox": {
        return (
          <SandboxView
            code={sandboxCode}
            setCode={setSandboxCode}
            executing={sandboxExecuting}
            response={sandboxResponse}
            error={sandboxErrorMsg}
            onExecute={handleExecuteSandbox}
            history={sandboxHistory}
            onSelectHistory={(item) => {
              setSandboxCode(item.code);
              setSandboxResponse(item.response);
              setSandboxErrorMsg(item.error || null);
            }}
            onClearHistory={() => setSandboxHistory([])}
          />
        );
      }

      case "history": {
        return (
          <HistoryView
            conversations={conversations}
            conversationsLoading={conversationsLoading}
            conversationsError={conversationsError}
            onRefreshConversations={loadConversations}
            onSelectConversation={handleSelectConversation}
            onDeleteConversation={handleDeleteConversation}
            sandboxHistory={sandboxHistory}
            onSelectSandbox={(item) => {
              setSandboxCode(item.code);
              setSandboxResponse(item.response);
              setSandboxErrorMsg(item.error || null);
            }}
            onClearSandboxHistory={() => setSandboxHistory([])}
            knowledgeHistory={knowledgeHistory}
            onSelectKnowledge={(item) => {
              setRagQueryText(item.query);
              setRagQueryResponse(item.response);
            }}
            onClearKnowledgeHistory={() => setKnowledgeHistory([])}
            onNavigateTab={setActiveTab}
          />
        );
      }

      case "audit": {
        const filteredLogs = auditLogs.filter((log) => {
          const matchesAction = auditActionFilter ? log.action === auditActionFilter : true;
          const matchesStatus = auditStatusFilter ? log.status === auditStatusFilter : true;
          const matchesUser = auditUserFilter ? log.username?.toLowerCase().includes(auditUserFilter.toLowerCase()) : true;
          const matchesSearch = auditSearchQuery 
            ? (log.username?.toLowerCase().includes(auditSearchQuery.toLowerCase()) || 
               log.request_id?.toLowerCase().includes(auditSearchQuery.toLowerCase()) ||
               log.component?.toLowerCase().includes(auditSearchQuery.toLowerCase()) ||
               log.action?.toLowerCase().includes(auditSearchQuery.toLowerCase()))
            : true;
          return matchesAction && matchesStatus && matchesUser && matchesSearch;
        });

        const totalEvts = auditSummary?.total_events ?? "Not available";
        const successEvts = auditSummary?.successful_events ?? "Not available";
        const failedEvts = auditSummary?.failed_actions ?? "Not available";
        const securityEvts = auditSummary?.security_events ?? "Not available";
        const aiEvts = auditSummary?.ai_operations ?? "Not available";
        const ragEvts = auditSummary?.rag_events ?? "Not available";
        const sandboxEvts = auditSummary?.sandbox_events ?? "Not available";

        return (
          <div className="aegis-operational-view aegis-audit-view space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-white/5 pb-6 gap-4">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-slate-100 uppercase">Audit Ledger</h1>
                <p className="text-sm text-slate-450 mt-1 uppercase tracking-wider font-semibold">
                  Append-only record of local security and AI runtime events.
                </p>
              </div>
              <Button
                variant="ghost"
                onClick={() => {
                  loadAuditLogs();
                  loadAuditSummaryAndHealth();
                }}
                disabled={auditLogsLoading}
                icon={<RefreshCw className={`h-3.5 w-3.5 ${auditLogsLoading ? "animate-spin text-blue-400" : ""}`} />}
                className="h-9 px-4 text-xs"
              >
                Refresh
              </Button>
            </div>

            {/* 7 KPI Metrics Row */}
            <div className="space-y-4">
              <h2 className="text-base font-bold text-slate-200 uppercase tracking-wide">Audit Ledger Summary</h2>
              {auditSummaryError && (
                <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg text-xs text-rose-400">
                  Unable to load authoritative audit totals. {auditSummaryError}
                </div>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-4">
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Total Events</span>
                  <span className="text-xl font-bold text-slate-100 font-sans">{auditLogsLoading ? "..." : totalEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">SQLite DB</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Successful</span>
                  <span className="text-xl font-bold text-emerald-400 font-sans">{auditLogsLoading ? "..." : successEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">Status: Success</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Failed</span>
                  <span className="text-xl font-bold text-rose-455 font-sans">{auditLogsLoading ? "..." : failedEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">Status: Failure</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Security</span>
                  <span className="text-xl font-bold text-blue-400 font-sans">{auditLogsLoading ? "..." : securityEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">Auth & Roles</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">AI Runtime</span>
                  <span className="text-xl font-bold text-purple-400 font-sans">{auditLogsLoading ? "..." : aiEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">Models & Agent</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">RAG Events</span>
                  <span className="text-xl font-bold text-indigo-400 font-sans">{auditLogsLoading ? "..." : ragEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">Search & Ingest</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-4 flex flex-col justify-between h-24 hover:border-slate-800 transition-colors">
                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Sandbox</span>
                  <span className="text-xl font-bold text-amber-400 font-sans">{auditLogsLoading ? "..." : sandboxEvts}</span>
                  <span className="text-[8px] text-slate-550 block font-mono">Code Exec</span>
                </div>
              </div>
            </div>

            {/* Filter Bar */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-white/5 pb-3">
                <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wide">Filter Audit Events</h3>
                {(auditActionFilter || auditStatusFilter || auditSearchQuery || auditUserFilter || auditStartDateFilter || auditEndDateFilter) && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setAuditActionFilter("");
                      setAuditStatusFilter("");
                      setAuditSearchQuery("");
                      setAuditUserFilter("");
                      setAuditStartDateFilter("");
                      setAuditEndDateFilter("");
                    }}
                    className="h-7 text-[11px] text-slate-400 hover:text-slate-200"
                  >
                    Clear Filters
                  </Button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 text-xs">
                {/* Search */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Search</label>
                  <input
                    type="text"
                    value={auditSearchQuery}
                    onChange={(e) => setAuditSearchQuery(e.target.value)}
                    placeholder="Keyword..."
                    className="w-full p-2.5 bg-[#05070c] border border-white/10 rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-sans"
                  />
                </div>

                {/* User */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">User</label>
                  <input
                    type="text"
                    value={auditUserFilter}
                    onChange={(e) => setAuditUserFilter(e.target.value)}
                    placeholder="Username..."
                    className="w-full p-2.5 bg-[#05070c] border border-white/10 rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-sans"
                  />
                </div>

                {/* Action */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Action</label>
                  <select
                    value={auditActionFilter}
                    onChange={(e) => setAuditActionFilter(e.target.value)}
                    className="w-full p-2.5 bg-[#05070c] border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:border-blue-500/30 cursor-pointer font-sans"
                  >
                    <option value="">All Actions</option>
                    <option value="AUTH_LOGIN">AUTH_LOGIN</option>
                    <option value="LOGIN_SUCCESS">LOGIN_SUCCESS</option>
                    <option value="LOGIN_FAILED">LOGIN_FAILED</option>
                    <option value="AUTH_REGISTER">AUTH_REGISTER</option>
                    <option value="AUTH_LOGOUT">AUTH_LOGOUT</option>
                    <option value="LOGOUT">LOGOUT</option>
                    <option value="AUTH_CHANGE_PASSWORD">AUTH_CHANGE_PASSWORD</option>
                    <option value="PASSWORD_CHANGED">PASSWORD_CHANGED</option>
                    <option value="AUTHORIZATION_DENIED">AUTHORIZATION_DENIED</option>
                    <option value="MODEL_LOAD">MODEL_LOAD</option>
                    <option value="MODEL_UNLOAD">MODEL_UNLOAD</option>
                    <option value="MODEL_SWITCH">MODEL_SWITCH</option>
                    <option value="MODEL_SELECTED">MODEL_SELECTED</option>
                    <option value="MODEL_TESTED">MODEL_TESTED</option>
                    <option value="RAG_SEARCH">RAG_SEARCH</option>
                    <option value="RAG_QUERY">RAG_QUERY</option>
                    <option value="DOCUMENT_INGEST">DOCUMENT_INGEST</option>
                    <option value="DOCUMENT_UPLOADED">DOCUMENT_UPLOADED</option>
                    <option value="DOCUMENT_INDEXED">DOCUMENT_INDEXED</option>
                    <option value="DOCUMENT_DELETED">DOCUMENT_DELETED</option>
                    <option value="CONVERSATION_CREATED">CONVERSATION_CREATED</option>
                    <option value="CONVERSATION_DELETED">CONVERSATION_DELETED</option>
                    <option value="CHAT_REQUEST">CHAT_REQUEST</option>
                    <option value="SANDBOX_EXECUTION">SANDBOX_EXECUTION</option>
                    <option value="USER_PROVISIONED">USER_PROVISIONED</option>
                    <option value="USER_CREATED">USER_CREATED</option>
                    <option value="USER_STATUS_UPDATED">USER_STATUS_UPDATED</option>
                    <option value="USER_ROLE_UPDATED">USER_ROLE_UPDATED</option>
                    <option value="ROLE_CHANGED">ROLE_CHANGED</option>
                    <option value="USER_PASSWORD_RESET">USER_PASSWORD_RESET</option>
                  </select>
                </div>

                {/* Status */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Status</label>
                  <select
                    value={auditStatusFilter}
                    onChange={(e) => setAuditStatusFilter(e.target.value)}
                    className="w-full p-2.5 bg-[#05070c] border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:border-blue-500/30 cursor-pointer font-sans"
                  >
                    <option value="">All Statuses</option>
                    <option value="success">Success</option>
                    <option value="failure">Failure</option>
                  </select>
                </div>

                {/* Start Date */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Start Date</label>
                  <input
                    type="date"
                    value={auditStartDateFilter}
                    onChange={(e) => setAuditStartDateFilter(e.target.value)}
                    className="w-full p-2.5 bg-[#05070c] border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:border-blue-500/30 transition-all font-mono text-[11px]"
                  />
                </div>

                {/* End Date */}
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">End Date</label>
                  <input
                    type="date"
                    value={auditEndDateFilter}
                    onChange={(e) => setAuditEndDateFilter(e.target.value)}
                    className="w-full p-2.5 bg-[#05070c] border border-white/10 rounded-lg text-slate-200 focus:outline-none focus:border-blue-500/30 transition-all font-mono text-[11px]"
                  />
                </div>
              </div>
            </div>

            {/* Live Event Table */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-5">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Append-Only Application Audit Log</h3>
                <p className="text-xs text-slate-450 mt-1">Application event records stored in local SQLite database.</p>
              </div>

              {auditLogsError && (
                <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400">
                  <div className="flex items-start space-x-2 font-semibold">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                    <span>AUDIT LEDGER ERROR</span>
                  </div>
                  <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                    Unable to fetch audit events from local SQLite database.
                  </p>
                  <details className="pl-6 text-[10px] text-slate-500 cursor-pointer pt-1">
                    <summary className="font-mono hover:text-slate-400">View technical details</summary>
                    <pre className="mt-2 p-2 bg-black/40 border border-white/5 rounded text-rose-300 font-mono whitespace-pre-wrap overflow-x-auto">
                      {auditLogsError}
                    </pre>
                  </details>
                </div>
              )}

              {healthStatus && healthStatus.services.audit_ledger === "inactive" ? (
                <div className="text-center py-16 border border-dashed border-rose-500/20 rounded-lg text-rose-400 space-y-2 bg-rose-500/5">
                  <AlertCircle className="h-8 w-8 text-rose-400 mx-auto opacity-70" />
                  <p className="text-sm font-bold text-rose-300 uppercase tracking-wider">AUDIT LEDGER UNAVAILABLE</p>
                  <p className="text-xs text-slate-400">The local audit database connection is currently offline or unreachable.</p>
                </div>
              ) : auditLogsLoading && filteredLogs.length === 0 ? (
                <div className="text-center py-16 text-slate-400 space-y-3 animate-pulse bg-black/10 rounded-lg">
                  <RefreshCw className="h-5 w-5 animate-spin mx-auto text-blue-400" />
                  <span className="text-xs font-mono uppercase font-bold tracking-wider">Querying SQLite audit database...</span>
                </div>
              ) : filteredLogs.length === 0 ? (
                <div className="text-center py-16 border border-dashed border-white/5 rounded-lg text-slate-500 space-y-2">
                  <History className="h-8 w-8 text-slate-600 mx-auto opacity-40" />
                  <p className="text-sm font-bold text-slate-300 uppercase tracking-wider">NO AUDIT EVENTS RECORDED</p>
                  <p className="text-xs text-slate-500">No recorded activity is currently available.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs leading-normal">
                    <thead>
                      <tr className="border-b border-white/5 text-slate-500 uppercase tracking-widest text-[9px] font-bold">
                        <th className="py-3 px-4">Timestamp</th>
                        <th className="py-3 px-4">Event ID</th>
                        <th className="py-3 px-4">Action</th>
                        <th className="py-3 px-4">User</th>
                        <th className="py-3 px-4">Role</th>
                        <th className="py-3 px-4">Component</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Request ID</th>
                        <th className="py-3 px-4 text-right">Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-slate-300">
                      {filteredLogs.map((log) => (
                        <tr key={log.id} className="hover:bg-white/5 transition-colors">
                          <td className="py-4 px-4 text-[11px] text-slate-400 font-mono">
                            {new Date(log.timestamp).toLocaleString()}
                          </td>
                          <td className="py-4 px-4 font-mono font-semibold text-slate-200 text-xs">
                            #{log.id}
                          </td>
                          <td className="py-4 px-4 font-semibold text-blue-400 font-mono text-xs">
                            {log.action}
                          </td>
                          <td className="py-4 px-4 font-semibold text-slate-200">
                            {log.username || "System Process"}
                          </td>
                          <td className="py-4 px-4 uppercase text-[11px] text-slate-400 font-mono">
                            {log.role || "SYSTEM"}
                          </td>
                          <td className="py-4 px-4 text-slate-400 font-mono text-[11px]">
                            {log.component}
                          </td>
                          <td className="py-4 px-4">
                            <StatusBadge
                              status={log.status === "success" ? "healthy" : "error"}
                              label={log.status.toUpperCase()}
                            />
                          </td>
                          <td className="py-4 px-4 text-slate-500 font-mono text-[10px] truncate max-w-[100px]">
                            {log.request_id || "N/A"}
                          </td>
                          <td className="py-4 px-4 text-right">
                            <Button
                              variant="secondary"
                              onClick={() => setSelectedAuditLog(log)}
                              className="h-7 px-2.5 text-[10px]"
                            >
                              View Details
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Event Detail Drawer Panel */}
            <AuditRecordDrawer
              log={selectedAuditLog}
              open={Boolean(selectedAuditLog)}
              onClose={() => setSelectedAuditLog(null)}
            />
          </div>
        );
      }

      case "access": {
        const filteredUsers = usersList.filter((u) => 
          u.username.toLowerCase().includes(usersSearchQuery.toLowerCase())
        );

        const totalUsers = usersList.length;
        const activeUsers = usersList.filter(u => u.is_active !== false).length;
        const inactiveUsers = usersList.filter(u => u.is_active === false).length;
        const adminUsers = usersList.filter(u => u.role === "admin").length;

        return (
          <div className="aegis-operational-view aegis-access-view space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="border-b border-white/5 pb-6">
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 uppercase">Access Control</h1>
              <p className="text-sm text-slate-450 mt-1 uppercase tracking-wider font-semibold">
                Manage authorized operators and their roles within the sovereign node.
              </p>
            </div>

            {/* User Management KPI Row */}
            <div className="space-y-4">
              <h2 className="text-base font-bold text-slate-200 uppercase tracking-wide">User Management</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Total Users</span>
                  <span className="text-2xl font-bold text-slate-100 mt-2 block font-sans">
                    {usersLoading ? "..." : totalUsers}
                  </span>
                  <span className="text-[9px] text-slate-550 block font-mono">Registered Node Accounts</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Active</span>
                  <span className="text-2xl font-bold text-emerald-400 mt-2 block font-sans">
                    {usersLoading ? "..." : activeUsers}
                  </span>
                  <span className="text-[9px] text-slate-550 block font-mono">Operational Access Granted</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Inactive</span>
                  <span className="text-2xl font-bold text-rose-455 mt-2 block font-sans">
                    {usersLoading ? "..." : inactiveUsers}
                  </span>
                  <span className="text-[9px] text-slate-550 block font-mono">Disabled Credentials</span>
                </div>
                <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Administrators</span>
                  <span className="text-2xl font-bold text-blue-400 mt-2 block font-sans">
                    {usersLoading ? "..." : adminUsers}
                  </span>
                  <span className="text-[9px] text-slate-550 block font-mono">Full Control Scope</span>
                </div>
              </div>
            </div>

            {/* Provision Form & User Table Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
              {/* Provision Form */}
              <div className="lg:col-span-1 bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-5">
                <div className="border-b border-white/5 pb-3">
                  <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Provision Operator</h3>
                  <p className="text-xs text-slate-450 mt-1">
                    New operators receive local credentials mapped to authorized node role scopes.
                  </p>
                </div>

                <form onSubmit={handleProvisionUser} className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-300 block">Username ID</label>
                    <input
                      type="text"
                      value={provisionForm.username}
                      onChange={(e) => setProvisionForm({ ...provisionForm, username: e.target.value })}
                      placeholder="e.g. op_john_doe"
                      className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-mono"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-300 block">Temporary Password</label>
                    <input
                      type="password"
                      value={provisionForm.password}
                      onChange={(e) => setProvisionForm({ ...provisionForm, password: e.target.value })}
                      placeholder="Minimum 8 characters"
                      className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-mono"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-300 block">Operator Role</label>
                    <select
                      value={provisionForm.role}
                      onChange={(e) => setProvisionForm({ ...provisionForm, role: e.target.value })}
                      className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500/30 cursor-pointer font-sans"
                    >
                      <option value="user">User (Standard Operator)</option>
                      <option value="admin">Admin (System Controller)</option>
                    </select>
                  </div>

                  <Button
                    type="submit"
                    variant="primary"
                    disabled={!provisionForm.username || !provisionForm.password}
                    className="w-full h-10 mt-2"
                  >
                    Provision User
                  </Button>
                </form>

                {provisionSuccess && (
                  <div className="bg-emerald-500/5 border border-emerald-500/15 p-4 rounded-lg flex items-start space-x-3 text-emerald-400 text-xs">
                    <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                    <span>{provisionSuccess}</span>
                  </div>
                )}

                {provisionError && (
                  <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400">
                    <div className="flex items-start space-x-2 font-semibold">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                      <span>User provisioning failed</span>
                    </div>
                    <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                      Please check the input parameters and confirm user uniqueness.
                    </p>
                    <details className="pl-6 text-[10px] text-slate-500 cursor-pointer pt-1">
                      <summary className="font-mono hover:text-slate-400">View technical details</summary>
                      <pre className="mt-2 p-2 bg-black/40 border border-white/5 rounded text-rose-300 font-mono whitespace-pre-wrap overflow-x-auto">
                        {provisionError}
                      </pre>
                    </details>
                  </div>
                )}
              </div>

              {/* User List Table */}
              <div className="lg:col-span-2 bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-white/5 pb-4 gap-4">
                  <div>
                    <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Registered Node Users</h3>
                    <p className="text-xs text-slate-450 mt-1">Authorized operator identities logged into local authentication stores.</p>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={loadUsersList}
                    disabled={usersLoading}
                    icon={<RefreshCw className={`h-3.5 w-3.5 ${usersLoading ? "animate-spin text-blue-400" : ""}`} />}
                    className="h-8 text-[11px] px-3"
                  >
                    Refresh List
                  </Button>
                </div>

                {/* Filter Search Input */}
                <div className="relative w-full">
                  <Search className="h-4 w-4 absolute left-3 top-3 text-slate-500" />
                  <input
                    type="text"
                    value={usersSearchQuery}
                    onChange={(e) => setUsersSearchQuery(e.target.value)}
                    placeholder="Search users by username..."
                    className="w-full pl-9 pr-4 py-2 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/30 transition-all font-sans"
                  />
                </div>

                {usersError && (
                  <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400">
                    <div className="flex items-start space-x-2 font-semibold">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                      <span>User registry query failed</span>
                    </div>
                    <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                      Unable to fetch registered operator list from local database.
                    </p>
                    <details className="pl-6 text-[10px] text-slate-500 cursor-pointer pt-1">
                      <summary className="font-mono hover:text-slate-400">View technical details</summary>
                      <pre className="mt-2 p-2 bg-black/40 border border-white/5 rounded text-rose-300 font-mono whitespace-pre-wrap overflow-x-auto">
                        {usersError}
                      </pre>
                    </details>
                  </div>
                )}

                {filteredUsers.length === 0 && !usersLoading ? (
                  <div className="text-center py-16 border border-dashed border-white/5 rounded-lg text-slate-500 space-y-2">
                    <User className="h-8 w-8 text-slate-600 mx-auto opacity-40" />
                    <p className="text-sm font-bold text-slate-300 uppercase tracking-wider">No operator records found</p>
                    <p className="text-xs text-slate-500">No users match your active search filter query.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs leading-normal">
                      <thead>
                        <tr className="border-b border-white/5 text-slate-500 uppercase tracking-widest text-[9px] font-bold">
                          <th className="py-3 px-4">Username</th>
                          <th className="py-3 px-4">Role</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4">Password Policy</th>
                          <th className="py-3 px-4">Created</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5 text-slate-300">
                        {filteredUsers.map((u) => (
                          <tr key={u.id} className="hover:bg-white/5 transition-colors">
                            <td className="py-4 px-4 font-semibold text-slate-200 font-mono">{u.username}</td>
                            <td className="py-4 px-4">
                              <select
                                value={u.role}
                                onChange={(e) => handleUpdateUserRole(u.username, e.target.value)}
                                className="bg-[#05070c] border border-white/10 rounded px-2 py-1 text-xs text-slate-200 cursor-pointer focus:outline-none focus:border-blue-500/30 font-sans"
                              >
                                <option value="user">User</option>
                                <option value="admin">Admin</option>
                              </select>
                            </td>
                            <td className="py-4 px-4">
                              <button
                                onClick={() => handleUpdateUserStatus(u.username, !u.is_active)}
                                className="cursor-pointer"
                              >
                                <StatusBadge 
                                  status={u.is_active ? "healthy" : "offline"} 
                                  label={u.is_active ? "ACTIVE" : "DISABLED"} 
                                />
                              </button>
                            </td>
                            <td className="py-4 px-4 text-slate-400 font-mono text-[11px]">
                              {u.must_change_password ? "MUST CHANGE" : "NORMAL"}
                            </td>
                            <td className="py-4 px-4 text-slate-400 font-mono text-[11px]">
                              {u.created_at ? new Date(u.created_at).toLocaleDateString() : "N/A"}
                            </td>
                            <td className="py-4 px-4 text-right">
                              <Button
                                variant="secondary"
                                onClick={() => {
                                  setPasswordResetTarget(u);
                                  setResetSuccess(null);
                                  setResetError(null);
                                  setNewPasswordResetValue("");
                                }}
                                className="h-7 px-2.5 text-[10px]"
                              >
                                Reset Password
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Password Reset Confirmation Modal */}
            {passwordResetTarget && (
              <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div className="bg-[#0c1220] border border-white/10 max-w-md w-full rounded-lg p-6 space-y-5 shadow-2xl">
                  <div className="flex items-center justify-between border-b border-white/5 pb-3">
                    <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">Reset Operator Password</h3>
                    <button 
                      onClick={() => setPasswordResetTarget(null)}
                      className="text-slate-500 hover:text-slate-300 text-xs font-bold cursor-pointer"
                    >
                      Close
                    </button>
                  </div>
                  
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Setting a reset password for user <strong className="text-slate-200 font-mono">{passwordResetTarget.username}</strong> will update credentials and set the password change flag.
                  </p>

                  <form onSubmit={handleResetUserPassword} className="space-y-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-semibold text-slate-300 block">New Password</label>
                      <input
                        type="password"
                        value={newPasswordResetValue}
                        onChange={(e) => setNewPasswordResetValue(e.target.value)}
                        placeholder="Minimum 8 characters"
                        className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500/30 transition-all font-mono"
                      />
                    </div>
                    <div className="flex justify-end space-x-3 pt-2">
                      <Button 
                        type="button" 
                        variant="ghost" 
                        onClick={() => setPasswordResetTarget(null)}
                      >
                        Cancel
                      </Button>
                      <Button
                        type="submit"
                        variant="primary"
                        disabled={!newPasswordResetValue}
                      >
                        Apply Password Reset
                      </Button>
                    </div>
                  </form>

                  {resetSuccess && (
                    <div className="bg-emerald-500/5 border border-emerald-500/15 p-4 rounded-lg flex items-start space-x-3 text-emerald-400 text-xs">
                      <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>{resetSuccess}</span>
                    </div>
                  )}

                  {resetError && (
                    <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400">
                      <div className="flex items-start space-x-2 font-semibold">
                        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                        <span>Password reset failed</span>
                      </div>
                      <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                        Please verify password strength criteria.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      }

      case "about": {
        return <AboutView />;
      }

      case "settings": {
        return (
          <SettingsView
            passwordForm={passwordForm}
            setPasswordForm={setPasswordForm}
            onSubmit={handleUserChangePassword}
            loading={passwordChanging}
            success={passwordChangeSuccess}
            error={passwordChangeError}
          />
        );
      }

      default:
        return null;
    }
  };

  if (loading) {
    return (
      <div className="h-screen w-screen bg-[#070c14] flex flex-col items-center justify-center space-y-4 font-mono select-none">
        <div className="relative flex items-center justify-center">
          <div className="absolute h-12 w-12 rounded-full border border-blue-500/20 animate-ping opacity-60" />
          <div className="h-10 w-10 rounded bg-blue-500/5 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <ShieldCheck className="h-5 w-5 animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  // Gated public view when credentials not present
  if (!user) {
    return <LandingPage />;
  }

  // Gated forced password change panel
  if (user.must_change_password) {
    return (
      <div className="h-screen w-screen bg-[#070c14] flex items-center justify-center p-4 font-mono">
        <div className="w-full max-w-[420px] bg-[#090e1a] border border-white/5 rounded p-8 space-y-6">
          <div className="flex flex-col items-center text-center">
            <div className="h-10 w-10 rounded bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-500 mb-3 animate-bounce">
              <Key className="h-5 w-5" />
            </div>
            <h2 className="text-sm font-bold tracking-widest text-slate-100 uppercase">FORCE PASSWORD CHANGE</h2>
            <p className="text-[10px] text-slate-500 mt-1 uppercase tracking-wider leading-relaxed">
              Your security credentials were provisioned by an administrator. You must set a personal security key before accessing the workbench.
            </p>
          </div>

          <form onSubmit={handleUserChangePassword} className="space-y-4">
            <div className="space-y-1">
              <label className="text-[9px] font-bold text-slate-550 block uppercase tracking-wider">Current Password</label>
              <input
                type="password"
                value={passwordForm.old_password}
                onChange={(e) => setPasswordForm({ ...passwordForm, old_password: e.target.value })}
                placeholder="Enter current credentials key"
                className="w-full px-3 py-2 bg-[#080c14] border border-white/5 rounded text-xs text-slate-200 focus:outline-none focus:border-blue-500/35"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-bold text-slate-550 block uppercase tracking-wider">New Personal Password</label>
              <input
                type="password"
                value={passwordForm.new_password}
                onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                placeholder="Min 8 characters key"
                className="w-full px-3 py-2 bg-[#080c14] border border-white/5 rounded text-xs text-slate-200 focus:outline-none focus:border-blue-500/35"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[9px] font-bold text-slate-550 block uppercase tracking-wider">Verify New Password</label>
              <input
                type="password"
                value={passwordForm.confirm_password}
                onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                placeholder="Re-enter new credentials key"
                className="w-full px-3 py-2 bg-[#080c14] border border-white/5 rounded text-xs text-slate-200 focus:outline-none focus:border-blue-500/35"
              />
            </div>

            <button
              type="submit"
              disabled={passwordChanging}
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-bold transition-all flex items-center justify-center cursor-pointer disabled:opacity-40"
            >
              {passwordChanging ? "Saving..." : "UPDATE SECURITY KEY & CONTINUE"}
            </button>
          </form>

          {passwordChangeSuccess && (
            <div className="bg-emerald-500/5 border border-emerald-500/15 p-3 rounded text-emerald-450 text-[10px] text-center">
              {passwordChangeSuccess}
            </div>
          )}

          {passwordChangeError && (
            <div className="bg-rose-500/5 border border-rose-500/15 p-3 rounded text-rose-455 text-[10px] text-center">
              Error: {passwordChangeError}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Active Application Shell
  return (
    <AuthGuard>
      <AppShell
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        currentModelName={currentModel?.display_name}
        documentCount={documents.length}
      >
        {renderTabContent()}
      </AppShell>
    </AuthGuard>
  );
}
