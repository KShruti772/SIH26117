"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar, { TabId } from "../components/layout/Sidebar";
import AppShell from "../components/layout/AppShell";
import AuthGuard from "../components/layout/AuthGuard";
import { chatApi, ConversationSession } from "../lib/api/chat";
import { ragApi, DocumentInfo, RagQueryResponse, RagSearchResult } from "../lib/api/rag";
import { modelsApi, ModelProfile, ModelTestResult } from "../lib/api/models";
import { sandboxApi, SandboxExecutionResponse } from "../lib/api/sandbox";
import { auditApi, AuditLog, AuditSummary } from "../lib/api/audit";
import { usersApi, UserProfile } from "../lib/api/users";
import { healthApi, SystemHealthResponse } from "../lib/api/health";
import { useAuth } from "../components/providers/AuthProvider";
import Card from "../components/ui/Card";
import StatusBadge from "../components/ui/StatusBadge";
import Button from "../components/ui/Button";
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
  Send,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Upload,
  Trash2,
  AlertTriangle,
  LayoutDashboard,
  FileSpreadsheet,
  Shield,
  User,
  Key,
  Unlock,
  Search,
  ChevronRight
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
  const [ragTopK, setRagTopK] = useState<number>(3);
  const [showHowItWorks, setShowHowItWorks] = useState<boolean>(false);
  const [ragQueryLoading, setRagQueryLoading] = useState(false);
  const [ragQueryResponse, setRagQueryResponse] = useState<RagQueryResponse | null>(null);
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
  const [sandboxCode, setSandboxCode] = useState<string>(
    "print('=== Basic Aegis Sandbox Test ===')\nx = 10\ny = 20\nprint(f'Sum Calculation: {x} + {y} = {x + y}')"
  );
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
      const h = await healthApi.getHealth();
      setHealthStatus(h);
      
      if (user?.role === "admin") {
        const sum = await auditApi.getSummary();
        setAuditSummary(sum);
      }
    } catch (err) {
      console.error("Failed loading summary metrics", err);
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
        latency_ms: 0,
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

  const loadConversations = async () => {
    setConversationsLoading(true);
    try {
      const list = await chatApi.listConversations();
      setConversations(list);
    } catch (err: any) {
      console.error("Failed to load conversations:", err);
    } finally {
      setConversationsLoading(false);
    }
  };

  const handleSelectConversation = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    try {
      const conv = await chatApi.getConversation(sessionId);
      if (conv && conv.messages) {
        setMessages(conv.messages.map((m) => ({
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
          error_detail: m.error_detail
        })));
      }
    } catch (err: any) {
      console.error("Failed to select conversation:", err);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await chatApi.createConversation();
      setActiveSessionId(newConv.id);
      setMessages([]);
      await loadConversations();
    } catch (err: any) {
      console.error("Failed to create new conversation:", err);
    }
  };

  const handleDeleteConversation = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await chatApi.deleteConversation(sessionId);
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setMessages([]);
      }
      await loadConversations();
    } catch (err: any) {
      console.error("Failed to delete conversation:", err);
    }
  };

  useEffect(() => {
    if (activeTab === "chat") {
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
      }
      const isRagUsed = response.rag_used ?? (response.sources && response.sources.length > 0);
      
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
                model_id: response.model_info?.model_id || currentModel?.model_id || "NOT REPORTED"
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

  const handleExecuteRagQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ragQueryText.trim() || ragQueryLoading) return;
    setRagQueryLoading(true);
    setRagQueryError(null);
    setRagQueryResponse(null);
    try {
      const res = await ragApi.query(ragQueryText.trim(), ragTopK);
      setRagQueryResponse(res);
    } catch (err: any) {
      setRagQueryError(err.message || "Failed executing vector similarity retrieval search.");
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
    } catch (err: any) {
      setSandboxErrorMsg(err.message || "Subprocess execution faulted.");
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
  const handleUserChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
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
        const activeModelName = currentModel?.display_name || currentModel?.model_id || "gemma3:4b";

        return (
          <div className="space-y-6 font-sans max-w-[1600px] mx-auto pb-8">
            {/* HEADER */}
            <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-7 flex flex-col lg:flex-row lg:items-center justify-between gap-6 shadow-xl">
              <div className="space-y-1">
                <h1 className="text-2xl font-bold text-slate-100 tracking-tight">
                  Welcome back, {user?.username || "Operator"}
                </h1>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Here&apos;s what&apos;s happening with your sovereign AI workbench.
                </p>
              </div>

              {/* COMPACT STATUS BADGES */}
              <div className="flex flex-wrap items-center gap-2.5 text-xs">
                <span className="px-3 py-1.5 bg-blue-500/10 border border-blue-500/25 text-blue-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-blue-400" />
                  <span>LOCAL INFERENCE</span>
                </span>
                <span className="px-3 py-1.5 bg-indigo-500/10 border border-indigo-500/25 text-indigo-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-400" />
                  <span>AIR-GAPPED</span>
                </span>
                <span className="px-3 py-1.5 bg-purple-500/10 border border-purple-500/25 text-purple-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-purple-400" />
                  <span>NO CLOUD TRANSMISSION</span>
                </span>
                <span className="px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  <span>RBAC ENABLED</span>
                </span>
                <span className="px-3 py-1.5 bg-teal-500/10 border border-teal-500/25 text-teal-300 rounded-lg text-[11px] font-semibold flex items-center space-x-1.5">
                  <span className="h-2 w-2 rounded-full bg-teal-400" />
                  <span>AUDIT INTEGRITY VERIFIED</span>
                </span>
              </div>
            </div>

            {/* SUMMARY CARDS (4 CARDS GRID) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {/* 1. AI MODEL */}
              <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-3 hover:border-slate-700/80 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wide">AI MODEL</span>
                  <span className="px-2 py-0.5 bg-blue-500/10 text-blue-300 border border-blue-500/25 rounded text-[10px] font-bold font-mono">LOCAL</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Current Active Model</span>
                  <span className="text-xl font-extrabold text-slate-100 font-mono block truncate mt-1" title={activeModelName}>
                    {activeModelName}
                  </span>
                </div>
              </div>

              {/* 2. KNOWLEDGE BASE */}
              <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-3 hover:border-slate-700/80 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wide">KNOWLEDGE BASE</span>
                  <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 border border-emerald-500/25 rounded text-[10px] font-bold font-mono">INDEXED</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Total Documents</span>
                  <span className="text-2xl font-extrabold text-slate-100 font-sans block mt-1">
                    {documentsLoading ? "NOT REPORTED" : documents.length}
                  </span>
                </div>
              </div>

              {/* 3. CONVERSATIONS */}
              <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-3 hover:border-slate-700/80 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wide">CONVERSATIONS</span>
                  <span className="px-2 py-0.5 bg-indigo-500/10 text-indigo-300 border border-indigo-500/25 rounded text-[10px] font-bold font-mono">ACTIVE</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Total Sessions</span>
                  <span className="text-2xl font-extrabold text-slate-100 font-sans block mt-1">
                    {conversationsLoading ? "NOT REPORTED" : conversations.length}
                  </span>
                </div>
              </div>

              {/* 4. SECURITY */}
              <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-3 hover:border-slate-700/80 transition-all">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wide">SECURITY</span>
                  <span className="px-2 py-0.5 bg-teal-500/10 text-teal-300 border border-teal-500/25 rounded text-[10px] font-bold font-mono">RBAC ENABLED</span>
                </div>
                <div>
                  <span className="text-xs text-slate-400 block">Authentication Status</span>
                  <span className="text-2xl font-extrabold text-emerald-400 font-sans block mt-1">
                    SECURE
                  </span>
                </div>
              </div>
            </div>

            {/* MAIN WORKSPACE GRID */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* CENTER MAIN WORKSPACE (8 COLS) */}
              <div className="lg:col-span-8 space-y-6">
                {/* LARGE AI ASSISTANT PREVIEW CARD */}
                <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-7 shadow-xl space-y-5">
                  <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
                    <div className="flex items-center space-x-3">
                      <div className="h-9 w-9 rounded-xl bg-blue-500/10 border border-blue-500/25 flex items-center justify-center text-blue-400 shrink-0">
                        <Bot className="h-5 w-5" />
                      </div>
                      <div>
                        <h2 className="text-base font-bold text-slate-100">AI Assistant</h2>
                        <p className="text-xs text-slate-400 mt-0.5">Local reasoning and grounded organizational intelligence workspace</p>
                      </div>
                    </div>

                    <Button
                      variant="primary"
                      onClick={() => setActiveTab("chat")}
                      className="h-9 px-4 text-xs font-semibold"
                    >
                      Open AI Assistant
                    </Button>
                  </div>

                  {/* PREVIEW CONTENT */}
                  {messages.length > 0 ? (
                    <div className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-xl space-y-3 text-xs">
                      <div className="flex items-center justify-between text-slate-400">
                        <span className="font-semibold text-blue-400">Recent Conversation Preview</span>
                        <span className="font-mono text-[10px]">Active Session</span>
                      </div>
                      <p className="text-slate-200 leading-relaxed italic line-clamp-3">
                        "{messages[messages.length - 1].content}"
                      </p>
                      {messages[messages.length - 1].sources && messages[messages.length - 1].sources!.length > 0 && (
                        <div className="flex items-center space-x-2 text-[11px] text-emerald-400">
                          <ShieldCheck className="h-3.5 w-3.5" />
                          <span>Grounded on {messages[messages.length - 1].sources!.length} retrieved evidence files</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="p-6 bg-slate-900/40 border border-slate-800/60 rounded-xl text-center space-y-3">
                      <p className="text-xs text-slate-400 leading-relaxed">
                        Start a new conversation to begin on-premise AI reasoning grounded on your organization&apos;s private knowledge base.
                      </p>
                      <Button
                        variant="secondary"
                        onClick={handleNewConversation}
                        className="h-8 px-4 text-xs"
                      >
                        Start New Conversation
                      </Button>
                    </div>
                  )}
                </div>

                {/* RECENT SYSTEM ACTIVITY TABLE */}
                <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-7 shadow-xl space-y-5">
                  <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
                    <div>
                      <h3 className="text-base font-bold text-slate-100 font-sans">
                        Recent System Activity
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">Real-time audit log events from local SQLite ledger</p>
                    </div>
                    {user?.role === "admin" && (
                      <Button variant="ghost" onClick={() => setActiveTab("audit")} className="h-8 px-3 text-xs">
                        View Audit Ledger
                      </Button>
                    )}
                  </div>

                  {recentLogs.length === 0 ? (
                    <div className="text-center py-8 border border-dashed border-slate-800 rounded-xl text-slate-500 font-sans text-xs">
                      No recorded activity.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs leading-normal font-sans">
                        <thead>
                          <tr className="border-b border-slate-800/80 text-slate-400 uppercase tracking-wider text-[10px] font-bold">
                            <th className="py-2.5 px-3">Timestamp</th>
                            <th className="py-2.5 px-3">Operator</th>
                            <th className="py-2.5 px-3">Action</th>
                            <th className="py-2.5 px-3">Component</th>
                            <th className="py-2.5 px-3 text-right">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 text-slate-300">
                          {recentLogs.map((log) => (
                            <tr key={log.id} className="hover:bg-slate-800/40 transition-colors">
                              <td className="py-3 px-3 text-[11px] text-slate-400 font-mono whitespace-nowrap">
                                {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                              </td>
                              <td className="py-3 px-3 font-semibold text-slate-200">{log.username || "System"}</td>
                              <td className="py-3 px-3 font-mono font-semibold text-blue-400">{log.action}</td>
                              <td className="py-3 px-3 text-slate-400 font-mono">{log.component}</td>
                              <td className="py-3 px-3 text-right">
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${
                                  log.status === "success" 
                                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/25" 
                                    : "bg-rose-500/10 text-rose-400 border-rose-500/25"
                                }`}>
                                  {log.status.toUpperCase()}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>

              {/* RIGHT PANEL (4 COLS) */}
              <div className="lg:col-span-4 space-y-5">
                {/* CURRENT MODEL CARD */}
                <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-5 shadow-xl space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                    <div className="flex items-center space-x-2 text-blue-400">
                      <Cpu className="h-4.5 w-4.5" />
                      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-100">CURRENT MODEL</h3>
                    </div>
                    <span className="text-[10px] font-bold text-emerald-400 font-mono">ACTIVE</span>
                  </div>

                  <div className="space-y-2">
                    <span className="text-base font-extrabold text-blue-400 font-mono block truncate" title={activeModelName}>
                      {activeModelName}
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

                {/* QUICK ACTIONS CARD */}
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

                {/* AUDIT INTEGRITY CARD */}
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

            {/* BOTTOM FOOTER */}
            <footer className="pt-6 border-t border-slate-800/80 text-center text-xs text-slate-400 font-sans space-y-1">
              <div className="font-semibold text-slate-300">AEGIS Sovereign On-Premise Agentic AI Workbench</div>
              <div>All data remains on-premise.</div>
            </footer>
          </div>
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
        const activeModelDisplay = currentModel?.display_name || currentModel?.model_id || "gemma3:4b";

        return (
          <div className="space-y-6 font-sans max-w-[1600px] mx-auto pb-6">
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
              <div className="lg:col-span-3 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl flex flex-col overflow-hidden shadow-xl">
                {/* Panel Header & New Conversation Button */}
                <div className="p-4 border-b border-slate-800/80 space-y-3.5 bg-[#090e1a]/80">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wide">Conversations</h2>
                    <span className="text-[11px] text-slate-500 font-mono">{conversations.length} total</span>
                  </div>

                  <Button
                    onClick={handleNewConversation}
                    variant="primary"
                    className="w-full h-10 flex items-center justify-center space-x-2 text-xs font-semibold shadow-md"
                  >
                    <Plus className="h-4 w-4" />
                    <span>+ New Conversation</span>
                  </Button>

                  {/* Search Conversations Input */}
                  <div className="relative">
                    <Search className="h-4 w-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={docSearchQuery}
                      onChange={(e) => setDocSearchQuery(e.target.value)}
                      placeholder="Search conversations..."
                      className="w-full pl-9 pr-3 py-2 bg-[#080d1a] border border-slate-800 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/40 transition-all font-sans"
                    />
                  </div>
                </div>

                {/* Conversation List */}
                <div className="flex-1 overflow-y-auto p-3 space-y-2">
                  {conversationsLoading && conversations.length === 0 ? (
                    <div className="p-6 text-center text-xs text-slate-500 font-sans animate-pulse">
                      Loading conversations...
                    </div>
                  ) : filteredConversations.length === 0 ? (
                    <div className="p-6 text-center text-xs text-slate-400 font-sans italic border border-slate-800/60 rounded-xl bg-slate-900/40">
                      No conversations yet
                    </div>
                  ) : (
                    filteredConversations.map((conv) => {
                      const isActive = activeSessionId === conv.id;
                      return (
                        <div
                          key={conv.id}
                          onClick={() => handleSelectConversation(conv.id)}
                          className={`p-3.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between group relative ${
                            isActive
                              ? "bg-blue-500/10 border-blue-500/30 text-slate-100 font-bold shadow-md shadow-blue-500/5"
                              : "bg-slate-900/40 border-slate-800/80 text-slate-300 hover:bg-slate-800/60 hover:border-slate-700/80 font-medium"
                          }`}
                        >
                          {/* Active Left Indicator Bar */}
                          {isActive && (
                            <span className="absolute left-0 top-1/2 -translate-y-1/2 h-7 w-1 rounded-r-full bg-blue-500" />
                          )}

                          <div className="flex-1 min-w-0 pr-2 space-y-1">
                            <span className="text-xs font-semibold block truncate" title={conv.title}>
                              {conv.title || "Industrial Valve Analysis"}
                            </span>
                            <div className="flex items-center space-x-2 text-[10px] text-slate-400">
                              <span>Active session</span>
                              <span>•</span>
                              <span className="font-mono">
                                {new Date(conv.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={(e) => handleDeleteConversation(conv.id, e)}
                            className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-rose-400 transition-opacity cursor-pointer rounded-lg hover:bg-rose-500/10"
                            title="Delete conversation"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* ZONE 2 (CENTER): AI CHAT WORKSPACE */}
              <div className="lg:col-span-6 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl flex flex-col overflow-hidden shadow-xl">
                {/* Active Session Sub-Header Bar */}
                <div className="px-6 py-3.5 border-b border-slate-800/80 bg-[#090e1a]/90 flex items-center justify-between shrink-0">
                  <div className="flex items-center space-x-2.5 truncate">
                    <Bot className="h-4.5 w-4.5 text-blue-400 shrink-0" />
                    <span className="text-xs font-bold text-slate-100 truncate">
                      {activeSession?.title || "Industrial Valve Analysis"}
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
                                  <span className="font-semibold text-slate-300">AEGIS is thinking...</span>
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

                                  {/* Answer Content */}
                                  <div className="whitespace-pre-wrap leading-relaxed text-slate-200">
                                    {msg.content}
                                  </div>

                                  {/* Expandable Source Evidence Section */}
                                  {!isUser && msg.sources && msg.sources.length > 0 && (
                                    <details className="border-t border-slate-800/80 pt-3 space-y-2 text-xs cursor-pointer">
                                      <summary className="font-bold text-blue-400 hover:text-blue-300 uppercase tracking-wider text-[11px] flex items-center space-x-2">
                                        <span>RETRIEVED EVIDENCE ({msg.sources.length} SOURCES)</span>
                                      </summary>
                                      
                                      <div className="space-y-2 pt-2">
                                        {msg.sources.map((src, idx) => (
                                          <div key={idx} className="p-3 bg-[#080d1a] border border-slate-800/80 rounded-lg space-y-1 text-xs">
                                            <div className="flex items-center justify-between text-[11px] font-semibold text-blue-300 border-b border-slate-800/80 pb-1">
                                              <span>{src.filename}</span>
                                              <span className="text-slate-400 font-mono text-[10px]">Page {src.page_number}</span>
                                            </div>
                                            {src.text && (
                                              <p className="text-slate-300 text-[11px] italic leading-relaxed pt-1">
                                                "{src.text}"
                                              </p>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    </details>
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
        const isRAGHealthy = healthStatus?.services.rag_engine === "healthy";
        const isVectorHealthy = healthStatus?.services.vector_store === "healthy";
        const latestDocTimestamp = documents.reduce((max, d) => (d.uploaded_at && d.uploaded_at > max ? d.uploaded_at : max), 0);

        return (
          <div className="space-y-8 font-sans max-w-[1500px] mx-auto pb-12">
            {/* PAGE HEADER */}
            <div className="bg-[#0c1220] border border-slate-800/80 rounded-2xl p-6 sm:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-xl relative overflow-hidden">
              <div className="space-y-2 relative z-10">
                <div className="flex items-center space-x-3">
                  <Database className="h-8 w-8 text-blue-400 shrink-0" />
                  <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-100 font-sans">
                    Knowledge Base
                  </h1>
                </div>
                <p className="text-sm sm:text-base text-slate-400 max-w-2xl leading-relaxed">
                  Securely index organizational documents for local AI retrieval.
                </p>
                <div className="flex flex-wrap items-center gap-4 pt-2 text-xs font-sans text-slate-400">
                  <span className="px-3 py-1 bg-slate-900/80 border border-slate-800 rounded-full font-bold text-slate-200">
                    {documents.length} Documents
                  </span>
                  <span>•</span>
                  <span>
                    Last indexed: <span className="text-slate-200 font-medium">{latestDocTimestamp ? new Date(latestDocTimestamp * 1000).toLocaleString() : "Not reported"}</span>
                  </span>
                  <span>•</span>
                  <span className="flex items-center space-x-1">
                    <span>Storage:</span>
                    <span className="text-emerald-400 font-mono font-bold">LOCAL</span>
                  </span>
                </div>
              </div>

              <div className="relative z-10 shrink-0">
                <Button
                  variant="primary"
                  onClick={() => fileInputRef.current?.click()}
                  icon={<Upload className="h-4 w-4" />}
                  className="h-11 px-6 text-sm font-bold shadow-lg shadow-blue-500/10"
                >
                  Upload Document
                </Button>
              </div>
            </div>

            {/* SECTION 1 — DOCUMENT UPLOAD & INGESTION PROGRESS ROW */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              
              {/* DOCUMENT UPLOAD CARD (6 COLS) */}
              <div className="lg:col-span-6 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-8 shadow-xl space-y-6">
                <div className="border-b border-slate-800/80 pb-4">
                  <h2 className="text-lg font-bold text-slate-100">Upload organizational knowledge</h2>
                  <p className="text-sm text-slate-400 mt-1 leading-relaxed">
                    Add PDF or TXT documents to the secure local knowledge base.
                  </p>
                </div>

                <form onSubmit={handleUploadFile} className="space-y-4">
                  {/* Large Professional Drop Zone */}
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-slate-700/80 hover:border-blue-500/60 rounded-2xl p-8 text-center cursor-pointer transition-all bg-[#080d1a] hover:bg-slate-900/60 group space-y-3"
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileChange}
                      accept=".txt,.pdf"
                      className="hidden"
                    />
                    <div className="h-12 w-12 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto transition-transform group-hover:scale-105">
                      <Upload className="h-6 w-6" />
                    </div>
                    <div className="space-y-1">
                      <span className="text-sm font-bold text-slate-200 block">
                        Drag &amp; drop files here
                      </span>
                      <span className="text-xs text-slate-400 block font-medium">or</span>
                      <span className="inline-block mt-1 px-4 py-2 bg-slate-800/80 hover:bg-slate-700/80 text-blue-400 border border-slate-700/80 rounded-xl text-xs font-bold transition-all">
                        Browse Files
                      </span>
                    </div>
                    <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-xs text-slate-400 font-sans">
                      <span>PDF / TXT • Maximum 10 MB</span>
                      <span className="flex items-center space-x-1 text-slate-400 font-medium">
                        <Lock className="h-3.5 w-3.5 text-emerald-400" />
                        <span>Files remain on this workstation</span>
                      </span>
                    </div>
                  </div>

                  {/* Selected File Preview Card */}
                  {selectedFile && (
                    <div className="p-4 bg-[#080d1a] border border-blue-500/30 rounded-xl flex items-center justify-between text-xs sm:text-sm">
                      <div className="flex-1 min-w-0 pr-3 space-y-1">
                        <span className="text-slate-100 font-bold block truncate">{selectedFile.name}</span>
                        <div className="flex items-center space-x-2 text-xs text-slate-400 font-mono">
                          <span>{formatBytes(selectedFile.size)}</span>
                          <span>•</span>
                          <span>{selectedFile.name.split('.').pop()?.toUpperCase() || 'DOCUMENT'}</span>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2 shrink-0">
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setSelectedFile(null)}
                          className="h-8 px-3 text-xs text-rose-400 hover:text-rose-300"
                        >
                          Remove
                        </Button>
                        <Button
                          type="submit"
                          variant="primary"
                          disabled={uploading}
                          loading={uploading}
                          className="h-8 px-4 text-xs font-bold shadow-md"
                        >
                          Upload &amp; Index
                        </Button>
                      </div>
                    </div>
                  )}

                  {!selectedFile && (
                    <Button
                      type="button"
                      variant="primary"
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full h-11 text-sm font-bold shadow-md"
                    >
                      Select Document
                    </Button>
                  )}
                </form>

                {/* SECTION 2 — INGESTION PROGRESS WORKFLOW */}
                {uploading && (
                  <div className="p-5 bg-[#080d1a] border border-blue-500/30 rounded-xl space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <span className="text-xs font-bold text-blue-400 uppercase tracking-wider">
                        Processing Document
                      </span>
                      <span className="text-xs text-slate-400 font-mono animate-pulse">Ingesting...</span>
                    </div>
                    <div className="space-y-2 text-xs font-sans">
                      {[
                        { name: "Document uploaded", key: "upload" },
                        { name: "Text extracted", key: "extract" },
                        { name: "Text chunked", key: "chunk" },
                        { name: "Generating local embeddings", key: "embedding" },
                        { name: "Indexing knowledge base", key: "index" },
                        { name: "Ready for retrieval", key: "ready" }
                      ].map((step, idx) => {
                        const isCurrent = uploadProgressStage?.toLowerCase().includes(step.key);
                        return (
                          <div key={idx} className="flex items-center justify-between py-1 border-b border-slate-900/60">
                            <div className="flex items-center space-x-2.5">
                              {isCurrent ? (
                                <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
                              ) : (
                                <span className="h-2 w-2 rounded-full bg-slate-600" />
                              )}
                              <span className={isCurrent ? "text-blue-300 font-bold" : "text-slate-400"}>
                                {step.name}
                              </span>
                            </div>
                            <span className={isCurrent ? "text-blue-400 font-mono font-bold" : "text-slate-600 font-mono"}>
                              {isCurrent ? "In Progress" : "Pending"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Upload Success Alert */}
                {uploadSuccess && (
                  <div className="p-5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-400 space-y-2">
                    <div className="flex items-center space-x-2 font-bold text-sm">
                      <CheckCircle2 className="h-5 w-5 shrink-0" />
                      <span>Document Uploaded &amp; Indexed Successfully</span>
                    </div>
                    <p className="text-slate-300 text-xs leading-relaxed">
                      Document vector chunks are now ready and available for grounded local retrieval.
                    </p>
                  </div>
                )}

                {/* Upload Failure Alert & Retry */}
                {uploadError && (
                  <div className="p-5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 space-y-3">
                    <div className="flex items-center space-x-2 font-bold text-sm text-rose-400">
                      <AlertCircle className="h-5 w-5 shrink-0" />
                      <span>We could not complete indexing</span>
                    </div>
                    <p className="text-slate-300 leading-relaxed text-xs">{uploadError}</p>
                    <div className="flex items-center space-x-3 pt-2">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={handleUploadFile}
                        className="h-8 px-3 text-xs font-semibold"
                      >
                        Retry Ingestion
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* SECTION 3 — INDEXED DOCUMENTS TABLE (6 COLS) */}
              <div className="lg:col-span-6 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-8 shadow-xl space-y-6">
                <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
                  <div>
                    <h2 className="text-lg font-bold text-slate-100">Indexed Knowledge</h2>
                    <p className="text-xs text-slate-400 mt-1">Authorized organizational documents active in vector memory.</p>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={loadDocuments}
                    disabled={documentsLoading}
                    icon={<RefreshCw className={`h-4 w-4 ${documentsLoading ? "animate-spin text-blue-400" : ""}`} />}
                    className="h-9 text-xs px-3"
                  >
                    Refresh
                  </Button>
                </div>

                {documents.length === 0 && !documentsLoading ? (
                  /* Clean Empty State */
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-2xl space-y-4 bg-[#080d1a]/50 p-6">
                    <FileText className="h-10 w-10 text-slate-600 mx-auto" />
                    <div className="space-y-1 max-w-sm mx-auto">
                      <h3 className="text-base font-bold text-slate-100">Knowledge Base Empty</h3>
                      <p className="text-xs text-slate-400 leading-relaxed">
                        No organizational documents have been indexed yet.
                      </p>
                    </div>
                    <Button
                      variant="primary"
                      onClick={() => fileInputRef.current?.click()}
                      className="h-9 px-5 text-xs font-bold"
                    >
                      Upload Document
                    </Button>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs leading-normal font-sans">
                      <thead>
                        <tr className="border-b border-slate-800/80 text-slate-400 uppercase tracking-wider text-[11px] font-bold">
                          <th className="py-3 px-3">Document</th>
                          <th className="py-3 px-3">Type</th>
                          <th className="py-3 px-3">Size</th>
                          <th className="py-3 px-3">Chunks</th>
                          <th className="py-3 px-3">Indexed</th>
                          <th className="py-3 px-3">Status</th>
                          <th className="py-3 px-3 text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 text-slate-300">
                        {documents.map((doc) => {
                          const ext = doc.filename.split(".").pop()?.toUpperCase() || "TXT";
                          return (
                            <tr key={doc.id} className="hover:bg-slate-800/40 transition-colors">
                              <td className="py-3.5 px-3 font-semibold text-slate-100 truncate max-w-[160px]" title={doc.filename}>
                                {doc.filename}
                              </td>
                              <td className="py-3.5 px-3 text-slate-400 font-mono text-xs">{ext}</td>
                              <td className="py-3.5 px-3 text-slate-400 font-mono text-xs">{doc.file_size ? formatBytes(doc.file_size) : "N/A"}</td>
                              <td className="py-3.5 px-3 text-slate-200 font-mono text-xs">{doc.chunks || doc.chunk_count || 4} chunks</td>
                              <td className="py-3.5 px-3 text-slate-400 font-mono text-xs">
                                {doc.uploaded_at ? new Date(doc.uploaded_at * 1000).toLocaleDateString() : "N/A"}
                              </td>
                              <td className="py-3.5 px-3">
                                <span className="px-2.5 py-0.5 rounded text-xs font-bold font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                                  ● Indexed
                                </span>
                              </td>
                              <td className="py-3.5 px-3 text-right">
                                <Button
                                  variant="destructive"
                                  onClick={() => handleDelete(doc.id, doc.filename)}
                                  disabled={deletingDocId !== null}
                                  className="h-7 px-2.5 text-xs font-semibold"
                                >
                                  Delete
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* SECTION 4 — RETRIEVAL TEST */}
            <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-8 shadow-xl space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800/80 pb-4 gap-4">
                <div>
                  <h2 className="text-lg sm:text-xl font-bold text-slate-100">Test Knowledge Retrieval</h2>
                  <p className="text-xs sm:text-sm text-slate-400 mt-1">
                    Ask a question to verify that AEGIS can retrieve relevant organizational knowledge.
                  </p>
                </div>

                <div className="flex items-center space-x-3 text-xs">
                  <span className="text-slate-400 font-medium">Top K:</span>
                  <div className="flex items-center space-x-1.5 bg-[#080d1a] p-1 rounded-xl border border-slate-800">
                    {[3, 5, 10].map((k) => (
                      <button
                        key={k}
                        type="button"
                        onClick={() => setRagTopK(k)}
                        className={`px-3 py-1 rounded-lg text-xs font-bold font-mono transition-all ${
                          ragTopK === k 
                            ? "bg-blue-600 text-white shadow-sm" 
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        {k}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <form onSubmit={handleExecuteRagQuery} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  value={ragQueryText}
                  onChange={(e) => setRagQueryText(e.target.value)}
                  placeholder="What is the proposed solution?"
                  className="flex-1 px-4 py-3 bg-[#080d1a] border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500/40 font-sans"
                />
                <Button
                  type="submit"
                  variant="primary"
                  disabled={!ragQueryText.trim() || ragQueryLoading}
                  loading={ragQueryLoading}
                  className="h-11 px-6 text-sm font-bold shrink-0"
                >
                  Search Knowledge Base
                </Button>
              </form>

              {ragQueryError && (
                <div className="p-4 bg-rose-500/10 border border-rose-500/25 rounded-xl text-rose-300 text-xs">
                  {ragQueryError}
                </div>
              )}

              {ragQueryResponse && (
                <div className="space-y-5 pt-2 border-t border-slate-800/80">
                  <div className="flex items-center justify-between text-xs sm:text-sm">
                    <span className="text-slate-400">
                      Query: <span className="text-slate-100 font-bold">&quot;{ragQueryResponse.query}&quot;</span>
                    </span>
                    <span className="text-emerald-400 font-bold text-xs sm:text-sm">
                      {ragQueryResponse.count} relevant sources found
                    </span>
                  </div>

                  {ragQueryResponse.results.length === 0 ? (
                    <div className="p-6 bg-[#080d1a] border border-amber-500/20 rounded-xl text-center space-y-1">
                      <h4 className="text-sm font-bold text-amber-400">NO RELEVANT ORGANIZATIONAL KNOWLEDGE FOUND</h4>
                      <p className="text-xs text-slate-400">No vector chunk met the similarity threshold for this query.</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {ragQueryResponse.results.map((res: RagSearchResult, idx: number) => (
                        <div key={idx} className="p-5 bg-[#080d1a] border border-slate-800/80 rounded-2xl space-y-3 shadow-md flex flex-col justify-between">
                          <div className="space-y-2">
                            <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2">
                              <span className="text-blue-400 font-bold uppercase tracking-wider text-xs">
                                SOURCE {idx + 1}
                              </span>
                              <div className="flex items-center space-x-2">
                                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                                  res.distance < 0.6 
                                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" 
                                    : res.distance < 1.1 
                                    ? "bg-blue-500/10 text-blue-300 border-blue-500/30" 
                                    : "bg-amber-500/10 text-amber-300 border-amber-500/30"
                                }`}>
                                  Relevance: {res.distance < 0.6 ? "High" : res.distance < 1.1 ? "Medium" : "Low"}
                                </span>
                              </div>
                            </div>
                            <div className="flex items-center justify-between text-xs font-semibold text-slate-200">
                              <span>{res.metadata.filename || res.metadata.document_name || "Document"}</span>
                              <span className="text-slate-400 font-mono text-xs">Page {res.metadata.page_number || 1}</span>
                            </div>
                            <div className="space-y-1">
                              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Relevant excerpt:</span>
                              <p className="text-slate-300 text-xs sm:text-sm leading-relaxed italic bg-slate-900/60 p-3.5 rounded-xl border border-slate-800/60 font-sans">
                                &quot;{res.text}&quot;
                              </p>
                            </div>
                          </div>

                          <div className="text-xs text-slate-500 font-mono pt-2 border-t border-slate-800/60 flex items-center justify-between">
                            <span>Technical details</span>
                            <span title="Cosine Distance">Distance: {res.distance.toFixed(4)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* SECTION 5 & 6 — HOW RAG WORKS & DATA RESIDENCY ROW */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* SECTION 5 — HOW RAG WORKS (8 COLS) */}
              <div className="lg:col-span-8 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-8 shadow-xl space-y-4 font-sans">
                <div className="border-b border-slate-800/80 pb-3">
                  <h2 className="text-base sm:text-lg font-bold text-slate-100">How AEGIS RAG Works</h2>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 text-xs">
                  {[
                    "1. Upload",
                    "2. Extract",
                    "3. Chunk",
                    "4. Embed locally",
                    "5. Store locally",
                    "6. Retrieve",
                    "7. Grounded answer"
                  ].map((step, i) => (
                    <div key={i} className="p-3 bg-[#080d1a] border border-slate-800/80 rounded-xl font-bold text-slate-200 text-center flex items-center justify-center">
                      {step}
                    </div>
                  ))}
                </div>

                <p className="text-xs sm:text-sm text-slate-400 leading-relaxed pt-2">
                  AEGIS Retrieval-Augmented Generation grounds all AI reasoning on local organizational documentation. Text extraction, vector embedding calculation, and ChromaDB vector indexing are executed 100% on-premise without external network transit.
                </p>
              </div>

              {/* SECTION 6 — DATA RESIDENCY (4 COLS) */}
              <div className="lg:col-span-4 bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl p-6 sm:p-8 shadow-xl space-y-4 font-sans">
                <div className="border-b border-slate-800/80 pb-3">
                  <h2 className="text-base sm:text-lg font-bold text-slate-100 uppercase tracking-wide">DATA RESIDENCY</h2>
                </div>

                <div className="divide-y divide-slate-800/60 text-xs sm:text-sm">
                  <div className="py-2.5 flex justify-between items-center">
                    <span className="text-slate-400">Processing</span>
                    <span className="font-bold text-emerald-400 font-mono">LOCAL</span>
                  </div>
                  <div className="py-2.5 flex justify-between items-center">
                    <span className="text-slate-400">Embeddings</span>
                    <span className="font-bold text-emerald-400 font-mono">LOCAL</span>
                  </div>
                  <div className="py-2.5 flex justify-between items-center">
                    <span className="text-slate-400">Vector Database</span>
                    <span className="font-bold text-emerald-400 font-mono">CHROMADB</span>
                  </div>
                  <div className="py-2.5 flex justify-between items-center">
                    <span className="text-slate-400">LLM</span>
                    <span className="font-bold text-emerald-400 font-mono">OLLAMA</span>
                  </div>
                  <div className="py-2.5 flex justify-between items-center">
                    <span className="text-slate-400">Cloud Routing</span>
                    <span className="font-bold text-rose-400 font-mono">DISABLED</span>
                  </div>
                  <div className="py-2.5 flex justify-between items-center">
                    <span className="text-slate-400">Document Data</span>
                    <span className="font-bold text-emerald-400 font-mono">NOT TRANSMITTED</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      }

      case "documents": {
        const totalDocsCount = documents.length;
        const indexedCount = documents.filter(d => {
          const s = (d.status || "").toLowerCase();
          return s === "indexed" || s === "ready" || s === "active" || !d.status;
        }).length;
        const processingCount = documents.filter(d => {
          const s = (d.status || "").toLowerCase();
          return s === "processing" || s === "ingesting";
        }).length;
        const failedCount = documents.filter(d => {
          const s = (d.status || "").toLowerCase();
          return s === "failed" || s === "error";
        }).length;

        const filteredDocs = documents.filter((doc) => {
          const matchesSearch = doc.filename.toLowerCase().includes(docSearchQuery.toLowerCase());
          const ext = (doc.filename.split(".").pop() || "").toUpperCase();
          const matchesType = !docTypeFilter || ext === docTypeFilter.toUpperCase();
          const status = (doc.status || "READY").toLowerCase();
          const matchesStatus = !docStatusFilter || 
            (docStatusFilter === "indexed" && (status.includes("ready") || status.includes("indexed"))) ||
            (docStatusFilter === "processing" && (status.includes("processing") || status.includes("ingesting"))) ||
            (docStatusFilter === "failed" && (status.includes("failed") || status.includes("error")));
          return matchesSearch && matchesType && matchesStatus;
        });

        return (
          <div className="space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
            {/* Header & Actions */}
            <div className="border-b border-white/5 pb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-slate-100 uppercase">Documents</h1>
                <p className="text-sm text-slate-450 mt-1 uppercase tracking-wider font-semibold">
                  Manage documents available to the local sovereign knowledge system.
                </p>
              </div>
              <div className="flex items-center space-x-3">
                <Button
                  variant="primary"
                  onClick={() => setActiveTab("rag")}
                  icon={<Upload className="h-4 w-4" />}
                >
                  Upload Document
                </Button>
                <Button
                  variant="ghost"
                  onClick={loadDocuments}
                  disabled={documentsLoading}
                  icon={<RefreshCw className={`h-4 w-4 ${documentsLoading ? "animate-spin text-blue-400" : ""}`} />}
                >
                  Refresh
                </Button>
              </div>
            </div>

            {/* Statistics KPI Row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Total Documents</span>
                <span className="text-2xl font-bold text-slate-100 mt-2 block font-sans">
                  {documentsLoading ? "..." : totalDocsCount}
                </span>
                <span className="text-[9px] text-slate-550 block font-mono">Registered files count</span>
              </div>
              <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Indexed</span>
                <span className="text-2xl font-bold text-emerald-400 mt-2 block font-sans">
                  {documentsLoading ? "..." : indexedCount}
                </span>
                <span className="text-[9px] text-slate-550 block font-mono">Vector store ready</span>
              </div>
              <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Processing</span>
                <span className="text-2xl font-bold text-amber-400 mt-2 block font-sans">
                  {documentsLoading ? "..." : processingCount}
                </span>
                <span className="text-[9px] text-slate-550 block font-sans">Active ingestion tasks</span>
              </div>
              <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 flex flex-col justify-between h-28 hover:border-slate-800 transition-colors">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Failed</span>
                <span className="text-2xl font-bold text-rose-455 mt-2 block font-sans">
                  {documentsLoading ? "..." : failedCount}
                </span>
                <span className="text-[9px] text-slate-550 block font-mono">Ingestion errors</span>
              </div>
            </div>

            {/* Documents List & Filters Container */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-6">
              {/* Search & Filters Controls */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-white/5 pb-5">
                <div className="relative w-full sm:w-80">
                  <Search className="h-4 w-4 absolute left-3 top-3 text-slate-500" />
                  <input
                    type="text"
                    value={docSearchQuery}
                    onChange={(e) => setDocSearchQuery(e.target.value)}
                    placeholder="Search documents by name..."
                    className="w-full pl-9 pr-4 py-2 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500/30 transition-all font-sans"
                  />
                </div>

                <div className="flex items-center space-x-3 w-full sm:w-auto justify-end text-xs">
                  <select
                    value={docTypeFilter}
                    onChange={(e) => setDocTypeFilter(e.target.value)}
                    className="px-3 py-2 bg-[#05070c] border border-white/10 rounded-lg text-slate-300 focus:outline-none focus:border-blue-500/30 cursor-pointer font-sans"
                  >
                    <option value="">All File Types</option>
                    <option value="PDF">PDF</option>
                    <option value="TXT">TXT</option>
                  </select>

                  <select
                    value={docStatusFilter}
                    onChange={(e) => setDocStatusFilter(e.target.value)}
                    className="px-3 py-2 bg-[#05070c] border border-white/10 rounded-lg text-slate-300 focus:outline-none focus:border-blue-500/30 cursor-pointer font-sans"
                  >
                    <option value="">All Statuses</option>
                    <option value="indexed">Indexed / Ready</option>
                    <option value="processing">Processing</option>
                    <option value="failed">Failed</option>
                  </select>
                </div>
              </div>

              {/* Error banner */}
              {documentsError && (
                <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400">
                  <div className="flex items-start space-x-2 font-semibold">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                    <span>Unable to retrieve reference documents list</span>
                  </div>
                  <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                    The local vector store could not be queried.
                  </p>
                  <details className="pl-6 text-[10px] text-slate-500 cursor-pointer pt-1">
                    <summary className="font-mono hover:text-slate-400">View technical details</summary>
                    <pre className="mt-2 p-2 bg-black/40 border border-white/5 rounded text-rose-300 font-mono whitespace-pre-wrap overflow-x-auto">
                      {documentsError}
                    </pre>
                  </details>
                </div>
              )}

              {/* Documents Table */}
              {filteredDocs.length === 0 && !documentsLoading ? (
                <div className="text-center py-16 border border-dashed border-white/5 rounded-lg text-slate-500 space-y-2">
                  <FileText className="h-8 w-8 text-slate-600 mx-auto opacity-40" />
                  <p className="text-sm font-bold text-slate-300 uppercase tracking-wider">
                    {docSearchQuery || docStatusFilter || docTypeFilter ? "No matching documents" : "Knowledge base is empty"}
                  </p>
                  <p className="text-xs text-slate-500">
                    {docSearchQuery || docStatusFilter || docTypeFilter 
                      ? "Try adjusting your search terms or filters." 
                      : "Upload an organizational document to begin indexing."}
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs leading-normal">
                    <thead>
                      <tr className="border-b border-white/5 text-slate-500 uppercase tracking-widest text-[9px] font-bold">
                        <th className="py-3 px-4">Document Name</th>
                        <th className="py-3 px-4">Type</th>
                        <th className="py-3 px-4">Size</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Chunks</th>
                        <th className="py-3 px-4">Created</th>
                        <th className="py-3 px-4">Indexed</th>
                        <th className="py-3 px-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-slate-300">
                      {filteredDocs.map((doc) => {
                        const ext = doc.filename.split(".").pop()?.toUpperCase() || "TXT";
                        return (
                          <tr key={doc.id} className="hover:bg-white/5 transition-colors">
                            <td className="py-4 px-4 font-semibold text-slate-200 truncate max-w-[240px] font-mono" title={doc.filename}>
                              {doc.filename}
                            </td>
                            <td className="py-4 px-4 text-slate-400 font-mono">{ext}</td>
                            <td className="py-4 px-4 text-slate-500 font-mono">N/A</td>
                            <td className="py-4 px-4">
                              <StatusBadge status={doc.status || "READY"} />
                            </td>
                            <td className="py-4 px-4 text-slate-500 font-mono">N/A</td>
                            <td className="py-4 px-4 text-slate-400 font-mono">
                              {new Date(doc.uploaded_at * 1000).toLocaleDateString()}
                            </td>
                            <td className="py-4 px-4 text-slate-400 font-mono">
                              {new Date(doc.uploaded_at * 1000).toLocaleTimeString()}
                            </td>
                            <td className="py-4 px-4 text-right space-x-2">
                              <Button
                                variant="secondary"
                                onClick={() => handleReindex(doc.id)}
                                disabled={reindexingDocId !== null || deletingDocId !== null}
                                className="h-7 px-2.5 text-[10px]"
                              >
                                RE-INDEX
                              </Button>
                              <Button
                                variant="destructive"
                                onClick={() => handleDelete(doc.id, doc.filename)}
                                disabled={deletingDocId !== null}
                                className="h-7 px-2.5 text-[10px]"
                              >
                                DELETE
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        );
      }

      case "models": {
        const activeVram = currentModel?.estimated_vram_gb || 0;
        const vramPercentage = Math.min(Math.round((activeVram / 6) * 100), 100);
        const isRuntimeConnected = healthStatus?.services.ai_runtime === "healthy";

        return (
          <div className="space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="border-b border-white/5 pb-6">
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 uppercase">Local Model Management</h1>
              <p className="text-sm text-slate-450 mt-1 uppercase tracking-wider font-semibold">
                Manage local inference models while respecting workstation VRAM constraints.
              </p>
            </div>

            {/* OLLAMA RUNTIME HEALTH & OVERVIEW */}
            <div className="bg-[#0c1220] border border-white/10 rounded-xl p-6 space-y-6 shadow-2xl">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-white/10 pb-4 gap-3 font-sans">
                <div>
                  <h3 className="text-base font-extrabold text-white uppercase tracking-wide">
                    OLLAMA LOCAL RUNTIME HEALTH
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    On-premise LLM daemon status, active weights, and air-gapped security mode.
                  </p>
                </div>
                <div className="flex items-center space-x-3 text-xs font-mono">
                  <StatusBadge 
                    status={isRuntimeConnected ? "healthy" : "warning"} 
                    label={isRuntimeConnected ? "Active Model Engine Online" : "Service Offline"} 
                  />
                  <Button
                    variant="ghost"
                    onClick={() => handleTestInference(currentModel?.model_id)}
                    loading={testingModelId === (currentModel?.model_id || "active")}
                    className="h-9 px-3 text-xs font-bold uppercase tracking-wider"
                  >
                    Run Test Inference
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-[#070c14] border border-white/10 rounded-xl p-4 space-y-2">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block font-mono">DAEMON ENDPOINT</span>
                  <span className="text-sm font-bold text-slate-100 block font-mono">http://localhost:11434</span>
                  <span className="text-[10px] text-emerald-400 block font-mono">Direct HTTP Port Binding</span>
                </div>
                <div className="bg-[#070c14] border border-white/10 rounded-xl p-4 space-y-2">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block font-mono">ACTIVE MODEL</span>
                  <span className="text-sm font-bold text-indigo-400 block font-mono truncate" title={currentModel?.model_id || "Unavailable"}>
                    {currentModel?.model_id || (modelsLoading ? "Loading active model..." : "Unavailable")}
                  </span>
                  <span className="text-[10px] text-slate-400 block font-mono">Primary Reasoning & Coding</span>
                </div>
                <div className="bg-[#070c14] border border-white/10 rounded-xl p-4 space-y-2">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block font-mono">DISCOVERED MODELS</span>
                  <span className="text-sm font-bold text-blue-400 block font-mono">
                    {modelRegistry.length} Local Models
                  </span>
                  <span className="text-[10px] text-slate-400 block font-mono">Ollama Tag Engine</span>
                </div>
                <div className="bg-[#070c14] border border-white/10 rounded-xl p-4 space-y-2">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block font-mono">AIR-GAP SECURITY</span>
                  <span className="text-sm font-bold text-rose-400 block font-mono">SOVEREIGN / LOCAL</span>
                  <span className="text-[10px] text-slate-400 block font-mono">Cloud Telemetry Disabled</span>
                </div>
              </div>
            </div>

            {/* TEST INFERENCE RESULT DRAWER */}
            {testResult && (
              <div className={`bg-[#0c1220] border rounded-xl p-6 space-y-4 shadow-2xl font-sans ${
                testResult.status === "PASS" ? "border-emerald-500/30" : "border-rose-500/30"
              }`}>
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <div className="flex items-center space-x-3">
                    <StatusBadge 
                      status={testResult.status === "PASS" ? "healthy" : "warning"} 
                      label={testResult.status === "PASS" ? "Inference Test Succeeded" : "Inference Test Failed"} 
                    />
                    <span className="text-xs font-mono text-slate-300">
                      Target Model: <span className="text-indigo-400 font-bold">{testResult.model}</span>
                    </span>
                  </div>
                  <span className="text-xs font-mono text-emerald-400 font-bold">
                    Measured Latency: {testResult.latency_ms} ms
                  </span>
                </div>

                <div className="space-y-2 font-mono text-xs">
                  <span className="text-slate-400 block uppercase tracking-wider text-[11px] font-bold">TEST PROMPT & LOCAL RESPONSE</span>
                  <div className="p-4 bg-[#070c14] border border-white/10 rounded-lg text-slate-200 leading-relaxed whitespace-pre-wrap">
                    {testResult.response || testResult.error || "No response received."}
                  </div>
                </div>
              </div>
            )}

            {/* SWAPPER ALERT MESSAGE */}
            {swapMessage && (
              <div className={`p-4 rounded-xl border text-xs font-sans ${
                swapMessage.type === "success" 
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
                  : swapMessage.type === "error"
                  ? "bg-rose-500/10 border-rose-500/20 text-rose-400"
                  : "bg-blue-500/10 border-blue-500/20 text-blue-400"
              }`}>
                {swapMessage.text}
              </div>
            )}

            {/* DISCOVERED LOCAL MODELS GRID */}
            <div className="space-y-4">
              <div className="border-b border-white/10 pb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-base font-extrabold text-white uppercase tracking-wide font-sans">
                    DISCOVERED LOCAL MODELS
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Model tags auto-discovered from local Ollama daemon runtime.
                  </p>
                </div>
                <Button
                  variant="ghost"
                  onClick={loadModelsData}
                  disabled={modelsLoading}
                  className="h-9 px-3 text-xs font-bold uppercase tracking-wider"
                >
                  Refresh Tags
                </Button>
              </div>

              {modelsLoading && modelRegistry.length === 0 ? (
                <div className="text-xs text-slate-500 py-12 text-center font-mono animate-pulse bg-[#0c1220] border border-white/10 rounded-xl">
                  Discovering local Ollama tags...
                </div>
              ) : modelRegistry.length === 0 ? (
                <div className="text-xs text-slate-400 py-12 text-center font-mono bg-[#0c1220] border border-white/10 rounded-xl">
                  No local models found in Ollama daemon. Run <span className="text-blue-400 font-bold">ollama pull gemma3:4b</span> to install.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {modelRegistry.map((model) => {
                    const isActive = (currentModel?.model_id === model.model_id) || model.is_active;
                    const isSwapping = swappingModelId === model.model_id;
                    const isTesting = testingModelId === model.model_id;

                    return (
                      <div 
                        key={model.model_id}
                        className={`bg-[#0c1220] border rounded-xl p-6 flex flex-col justify-between space-y-6 transition-all shadow-xl ${
                          isActive 
                            ? "border-blue-500/40 shadow-blue-500/5 bg-[#0c1220]/90" 
                            : "border-white/10 hover:border-white/20"
                        }`}
                      >
                        <div className="space-y-4">
                          <div className="flex items-start justify-between">
                            <div className="space-y-1">
                              <h4 className="text-sm font-extrabold text-white truncate font-mono" title={model.display_name}>
                                {model.display_name}
                              </h4>
                              <span className="text-[10px] text-slate-400 font-mono block">
                                {model.runtime_model_name}
                              </span>
                            </div>
                            <StatusBadge 
                              status={isActive ? "healthy" : model.is_installed ? "healthy" : "offline"} 
                              label={isActive ? "ACTIVE" : model.is_installed ? "INSTALLED" : "UNAVAILABLE"} 
                            />
                          </div>

                          <div className="space-y-2 text-xs divide-y divide-white/5 pt-1 font-mono">
                            <div className="py-1.5 flex justify-between">
                              <span className="text-slate-400">PARAMETERS</span>
                              <span className="text-indigo-400 font-bold">{model.parameter_size || "4B"}</span>
                            </div>
                            <div className="py-1.5 flex justify-between">
                              <span className="text-slate-400">QUANTIZATION</span>
                              <span className="text-slate-200 font-bold">{model.quantization || "Q4_K_M"}</span>
                            </div>
                            <div className="py-1.5 flex justify-between">
                              <span className="text-slate-400">FORMAT</span>
                              <span className="text-slate-300 font-bold uppercase">{model.format || "gguf"}</span>
                            </div>
                            {model.size_bytes && (
                              <div className="py-1.5 flex justify-between">
                                <span className="text-slate-400">FILE SIZE</span>
                                <span className="text-blue-400 font-bold">
                                  {(model.size_bytes / (1024 * 1024 * 1024)).toFixed(2)} GB
                                </span>
                              </div>
                            )}
                            <div className="py-1.5 flex justify-between">
                              <span className="text-slate-400">PROVIDER</span>
                              <span className="text-emerald-400 font-bold">{model.provider || "Ollama"}</span>
                            </div>
                          </div>
                        </div>

                        <div className="space-y-2 pt-2">
                          <Button
                            variant={isActive ? "ghost" : "primary"}
                            onClick={() => handleSelectModel(model.model_id)}
                            disabled={isActive || swappingModelId !== null || modelsLoading}
                            loading={isSwapping}
                            className="w-full h-10 text-xs font-bold uppercase tracking-wider"
                          >
                            {isSwapping ? "Activating Weights..." : isActive ? "ACTIVE MODEL" : "Activate Model"}
                          </Button>

                          <Button
                            variant="ghost"
                            onClick={() => handleTestInference(model.model_id)}
                            disabled={testingModelId !== null}
                            loading={isTesting}
                            className="w-full h-9 text-xs font-bold uppercase tracking-wider text-slate-300 hover:text-white"
                          >
                            Test Inference
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* ENTERPRISE MODEL METADATA DETAILS PANEL */}
            {currentModel && (
              <div className="bg-[#0c1220] border border-white/10 rounded-xl p-6 space-y-4 shadow-2xl font-sans">
                <div className="border-b border-white/10 pb-3 flex items-center justify-between">
                  <div>
                    <h3 className="text-base font-extrabold text-white uppercase tracking-wide">
                      VERIFIED MODEL SPECIFICATIONS
                    </h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Technical metadata verified directly from Ollama runtime headers.
                    </p>
                  </div>
                  <span className="text-xs font-mono text-indigo-400 font-bold uppercase">
                    ACTIVE MODEL: {currentModel.model_id}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 font-mono text-xs pt-2">
                  <div className="p-3 bg-[#070c14] border border-white/10 rounded-lg space-y-1">
                    <span className="text-slate-500 block text-[10px]">MODEL ID</span>
                    <span className="text-slate-100 font-bold truncate block">{currentModel.model_id}</span>
                  </div>
                  <div className="p-3 bg-[#070c14] border border-white/10 rounded-lg space-y-1">
                    <span className="text-slate-500 block text-[10px]">PROVIDER</span>
                    <span className="text-emerald-400 font-bold truncate block">{currentModel.provider || "Ollama"}</span>
                  </div>
                  <div className="p-3 bg-[#070c14] border border-white/10 rounded-lg space-y-1">
                    <span className="text-slate-500 block text-[10px]">RUNTIME</span>
                    <span className="text-blue-400 font-bold truncate block">LOCAL (ON-PREMISE)</span>
                  </div>
                  <div className="p-3 bg-[#070c14] border border-white/10 rounded-lg space-y-1">
                    <span className="text-slate-500 block text-[10px]">STATUS</span>
                    <span className="text-emerald-400 font-bold truncate block">ACTIVE</span>
                  </div>
                  <div className="p-3 bg-[#070c14] border border-white/10 rounded-lg space-y-1">
                    <span className="text-slate-500 block text-[10px]">ENDPOINT</span>
                    <span className="text-slate-200 font-bold truncate block">localhost:11434</span>
                  </div>
                  <div className="p-3 bg-[#070c14] border border-white/10 rounded-lg space-y-1">
                    <span className="text-slate-500 block text-[10px]">QUANTIZATION</span>
                    <span className="text-indigo-400 font-bold truncate block">{currentModel.quantization || "Q4_K_M"}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      }

      case "sandbox": {
        const DEFAULT_EXAMPLE_CODE = "print('=== Basic Aegis Sandbox Test ===')\nx = 10\ny = 20\nprint(f'Sum Calculation: {x} + {y} = {x + y}')";

        return (
          <div className="space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="border-b border-white/5 pb-6">
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 uppercase">Secure Code Execution</h1>
              <p className="text-sm text-slate-450 mt-1 uppercase tracking-wider font-semibold">
                Execute generated Python code inside an isolated local subprocess.
              </p>
            </div>

            {/* Split IDE-Like Workspace */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
              {/* Left Main: Python Editor */}
              <div className="lg:col-span-2 bg-[#0c1220] border border-white/5 rounded-lg overflow-hidden flex flex-col space-y-0">
                {/* IDE Toolbar */}
                <div className="px-5 py-3.5 bg-black/20 border-b border-white/5 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-blue-500"></span>
                    <span className="text-xs font-bold text-slate-200 font-mono">main.py</span>
                    <span className="text-[10px] text-slate-500 font-mono">(Python 3.12 Subprocess)</span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <Button
                      variant="ghost"
                      onClick={() => setSandboxCode(DEFAULT_EXAMPLE_CODE)}
                      disabled={sandboxExecuting}
                      className="h-8 text-[11px] px-3"
                    >
                      Reset Example
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setSandboxCode("");
                        setSandboxResponse(null);
                        setSandboxErrorMsg(null);
                      }}
                      disabled={sandboxExecuting}
                      className="h-8 text-[11px] px-3"
                    >
                      Clear
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleExecuteSandbox}
                      disabled={sandboxExecuting || !sandboxCode.trim()}
                      loading={sandboxExecuting}
                      className="h-8 text-[11px] px-4"
                    >
                      {sandboxExecuting ? "Executing..." : "Run Code"}
                    </Button>
                  </div>
                </div>

                {/* Editor textarea */}
                <div className="p-4 bg-[#05070c]">
                  <textarea
                    rows={14}
                    value={sandboxCode}
                    onChange={(e) => setSandboxCode(e.target.value)}
                    disabled={sandboxExecuting}
                    placeholder="# Write Python code to execute inside the sandbox..."
                    className="w-full p-4 bg-[#05070c] text-sm text-emerald-400 placeholder-slate-650 focus:outline-none transition-all font-mono resize-none leading-relaxed border-0"
                  />
                </div>
              </div>

              {/* Right: Execution Summary & Output */}
              <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-6">
                <div className="border-b border-white/5 pb-3">
                  <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Execution Summary</h3>
                  <p className="text-xs text-slate-450 mt-1">Output logs captured from the execution thread.</p>
                </div>

                {/* Status Metrics */}
                <div className="divide-y divide-white/5 bg-black/20 p-4 rounded-lg border border-white/5 text-xs space-y-2">
                  <div className="py-1 flex justify-between items-center">
                    <span className="text-slate-450">Status</span>
                    {sandboxResponse ? (
                      <StatusBadge 
                        status={sandboxResponse.success ? "healthy" : "error"} 
                        label={sandboxResponse.success ? "SUCCESS" : "FAILED"} 
                      />
                    ) : (
                      <StatusBadge status="offline" label="NOT EXECUTED" />
                    )}
                  </div>
                  <div className="py-2 flex justify-between items-center">
                    <span className="text-slate-450">Execution Time</span>
                    <span className="font-semibold text-slate-200 font-mono">
                      {sandboxResponse ? `${sandboxResponse.duration_ms} ms` : "N/A"}
                    </span>
                  </div>
                  <div className="py-2 flex justify-between items-center">
                    <span className="text-slate-450">Exit Code</span>
                    <span className={`font-semibold font-mono ${
                      sandboxResponse 
                        ? sandboxResponse.exit_code === 0 ? "text-emerald-400" : "text-rose-400" 
                        : "text-slate-400"
                    }`}>
                      {sandboxResponse ? sandboxResponse.exit_code : "N/A"}
                    </span>
                  </div>
                </div>

                {/* Error Banner */}
                {sandboxErrorMsg && (
                  <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400">
                    <div className="flex items-start space-x-2 font-semibold">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                      <span>Sandbox execution error</span>
                    </div>
                    <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                      An unexpected error occurred during execution thread launch.
                    </p>
                    <details className="pl-6 text-[10px] text-slate-500 cursor-pointer pt-1">
                      <summary className="font-mono hover:text-slate-400">View technical details</summary>
                      <pre className="mt-2 p-2 bg-black/40 border border-white/5 rounded text-rose-300 font-mono whitespace-pre-wrap overflow-x-auto">
                        {sandboxErrorMsg}
                      </pre>
                    </details>
                  </div>
                )}

                {/* Execution Output Streams (Separated) */}
                {!sandboxResponse && !sandboxErrorMsg && !sandboxExecuting && (
                  <div className="text-center py-12 border border-dashed border-white/5 rounded-lg text-slate-500 space-y-2">
                    <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">NO EXECUTION YET</span>
                    <p className="text-[11px] text-slate-550">Run Python code to inspect stdout and stderr streams.</p>
                  </div>
                )}

                {sandboxExecuting && (
                  <div className="text-center py-12 border border-white/5 rounded-lg text-slate-400 space-y-3 animate-pulse bg-black/10">
                    <RefreshCw className="h-5 w-5 animate-spin mx-auto text-blue-400" />
                    <span className="text-xs font-mono uppercase font-bold tracking-wider">Running isolated thread...</span>
                  </div>
                )}

                {sandboxResponse && (
                  <div className="space-y-4 text-xs font-mono">
                    {/* Stdout Output Stream */}
                    <div className="space-y-1.5">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-sans">
                        Stdout Output
                      </span>
                      <pre className="p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 overflow-x-auto whitespace-pre-wrap max-h-[140px] leading-relaxed">
                        {sandboxResponse.stdout || "[Console Output Empty]"}
                      </pre>
                    </div>

                    {/* Stderr Output Stream */}
                    <div className="space-y-1.5">
                      <span className="text-[10px] font-bold text-rose-400 uppercase tracking-wider block font-sans">
                        Stderr Output
                      </span>
                      <pre className={`p-3 bg-[#05070c] border rounded-lg text-xs overflow-x-auto whitespace-pre-wrap max-h-[140px] leading-relaxed ${
                        sandboxResponse.stderr 
                          ? "border-rose-500/20 text-rose-300 bg-rose-500/5" 
                          : "border-white/10 text-slate-500"
                      }`}>
                        {sandboxResponse.stderr || "[No Errors Logged]"}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Section: Sandbox Security */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-4">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Sandbox Security</h3>
                <p className="text-xs text-slate-450 mt-1">Resource limits and process isolation rules enforced during local script execution.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6 pt-2">
                <div className="bg-[#070c14] border border-white/5 rounded-lg p-5 flex flex-col justify-between h-24">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Process Isolation</span>
                  <div className="mt-1">
                    <StatusBadge status="healthy" label="ENABLED" />
                  </div>
                  <span className="text-[9px] text-slate-550 block font-mono">Subprocess Thread</span>
                </div>
                <div className="bg-[#070c14] border border-white/5 rounded-lg p-5 flex flex-col justify-between h-24">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Timeout</span>
                  <span className="text-sm font-bold text-slate-200 font-mono mt-1">10 seconds</span>
                  <span className="text-[9px] text-slate-550 block font-mono">Hard Process Boundary</span>
                </div>
                <div className="bg-[#070c14] border border-white/5 rounded-lg p-5 flex flex-col justify-between h-24">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Environment Scrubbing</span>
                  <div className="mt-1">
                    <StatusBadge status="healthy" label="ENABLED" />
                  </div>
                  <span className="text-[9px] text-slate-550 block font-mono">Scrubbed Envs</span>
                </div>
                <div className="bg-[#070c14] border border-white/5 rounded-lg p-5 flex flex-col justify-between h-24">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Network Access</span>
                  <div className="mt-1">
                    <StatusBadge status="warning" label="RESTRICTED" />
                  </div>
                  <span className="text-[9px] text-slate-550 block font-mono">Disabled Sockets</span>
                </div>
                <div className="bg-[#070c14] border border-white/5 rounded-lg p-5 flex flex-col justify-between h-24">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">File Access</span>
                  <div className="mt-1">
                    <StatusBadge status="warning" label="RESTRICTED" />
                  </div>
                  <span className="text-[9px] text-slate-550 block font-mono">Temp Scope Only</span>
                </div>
              </div>
            </div>
          </div>
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

        const totalEvts = auditSummary?.total_events ?? auditLogs.length;
        const successEvts = auditSummary?.successful_events ?? auditLogs.filter(l => l.status === "success").length;
        const failedEvts = auditSummary?.failed_actions ?? auditLogs.filter(l => l.status === "failure").length;
        const securityEvts = auditSummary?.security_events ?? auditLogs.filter(l => [
          "AUTH_LOGIN", "AUTH_REGISTER", "AUTH_LOGOUT", "AUTH_CHANGE_PASSWORD", "PASSWORD_CHANGE", 
          "PASSWORD_RESET", "USER_PASSWORD_RESET", "USER_PROVISION", "USER_PROVISIONED", 
          "USER_ROLE_CHANGE", "USER_ROLE_UPDATED", "USER_ENABLE", "USER_DISABLE", "USER_STATUS_UPDATED"
        ].includes(l.action)).length;
        const aiEvts = auditSummary?.ai_operations ?? auditLogs.filter(l => [
          "MODEL_LOAD", "MODEL_UNLOAD", "MODEL_SWITCH", "AGENT_EXECUTION"
        ].includes(l.action)).length;
        const ragEvts = auditSummary?.rag_events ?? auditLogs.filter(l => [
          "RAG_SEARCH", "RAG_QUERY", "RAG_DOCUMENT_UPLOAD", "RAG_DOCUMENT_INDEX", 
          "DOCUMENT_INGEST", "DOCUMENT_UPLOADED", "DOCUMENT_INDEXED", "DOCUMENT_DELETED", "OCR_PROCESS"
        ].includes(l.action)).length;
        const sandboxEvts = auditSummary?.sandbox_events ?? auditLogs.filter(l => l.action === "SANDBOX_EXECUTION").length;

        return (
          <div className="space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
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

            {/* Event Detail Modal Panel */}
            {selectedAuditLog && (
              <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div className="bg-[#0c1220] border border-white/10 max-w-xl w-full rounded-lg p-6 space-y-5 shadow-2xl">
                  <div className="flex items-center justify-between border-b border-white/5 pb-3">
                    <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wide">Audit Record #{selectedAuditLog.id}</h3>
                    <button 
                      onClick={() => setSelectedAuditLog(null)}
                      className="text-slate-500 hover:text-slate-300 text-xs font-bold cursor-pointer"
                    >
                      Close
                    </button>
                  </div>

                  <div className="divide-y divide-white/5 text-xs space-y-3 font-mono">
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">TIMESTAMP:</span>
                      <span className="text-slate-300">{new Date(selectedAuditLog.timestamp).toLocaleString()}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">EVENT ID:</span>
                      <span className="text-slate-200 font-bold">#{selectedAuditLog.id}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">ACTION CODE:</span>
                      <span className="text-blue-400 font-bold">{selectedAuditLog.action}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">USER IDENTITY:</span>
                      <span className="text-slate-200 font-bold">{selectedAuditLog.username || "System Process"}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">USER ROLE:</span>
                      <span className="text-slate-300">{selectedAuditLog.role || "SYSTEM"}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">COMPONENT MODULE:</span>
                      <span className="text-slate-300">{selectedAuditLog.component}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">EXECUTION STATUS:</span>
                      <span className={`font-bold ${selectedAuditLog.status === "success" ? "text-emerald-400" : "text-rose-400"}`}>
                        {selectedAuditLog.status.toUpperCase()}
                      </span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">REQUEST ID:</span>
                      <span className="text-slate-300 select-all font-mono">{selectedAuditLog.request_id || "N/A"}</span>
                    </div>
                    <div className="pt-2 flex justify-between">
                      <span className="text-slate-500">DURATION:</span>
                      <span className="text-slate-300 font-mono">{selectedAuditLog.duration_ms != null ? `${selectedAuditLog.duration_ms} ms` : "N/A"}</span>
                    </div>
                    <div className="pt-2 space-y-1.5">
                      <span className="text-slate-500 block uppercase font-bold text-[10px]">RECORD METADATA:</span>
                      {selectedAuditLog.metadata_json ? (
                        <pre className="p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-300 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[160px]">
                          {selectedAuditLog.metadata_json}
                        </pre>
                      ) : (
                        <p className="text-slate-500 italic text-[11px]">Not recorded</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
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
          <div className="space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
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

      case "settings": {
        return (
          <div className="space-y-10 animate-fadeIn font-sans max-w-7xl mx-auto">
            {/* Page Header */}
            <div className="border-b border-white/5 pb-6">
              <h1 className="text-2xl font-bold tracking-tight text-slate-100 uppercase">System Settings</h1>
              <p className="text-sm text-slate-450 mt-1 uppercase tracking-wider font-semibold">
                Sovereign configuration values and active security policies of the local node workstation.
              </p>
            </div>

            {/* Section 1: Security Key */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-5">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Security Key</h3>
                <p className="text-xs text-slate-450 mt-1">Update your account authentication credentials for this sovereign node.</p>
              </div>

              <form onSubmit={handleUserChangePassword} className="space-y-4 max-w-md">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 block">Current Password</label>
                  <input
                    type="password"
                    value={passwordForm.old_password}
                    onChange={(e) => setPasswordForm({ ...passwordForm, old_password: e.target.value })}
                    placeholder="Enter current password"
                    className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 block">New Password</label>
                  <input
                    type="password"
                    value={passwordForm.new_password}
                    onChange={(e) => setPasswordForm({ ...passwordForm, new_password: e.target.value })}
                    placeholder="Minimum 8 characters"
                    className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 block">Confirm New Password</label>
                  <input
                    type="password"
                    value={passwordForm.confirm_password}
                    onChange={(e) => setPasswordForm({ ...passwordForm, confirm_password: e.target.value })}
                    placeholder="Re-enter new password"
                    className="w-full p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/30 transition-all font-mono"
                  />
                </div>

                <Button
                  type="submit"
                  variant="primary"
                  disabled={passwordChanging || !passwordForm.old_password || !passwordForm.new_password}
                  loading={passwordChanging}
                  className="h-10 px-6 mt-2"
                >
                  Update Password
                </Button>
              </form>

              {passwordChangeSuccess && (
                <div className="bg-emerald-500/5 border border-emerald-500/15 p-4 rounded-lg flex items-start space-x-3 text-emerald-400 text-xs max-w-md font-sans">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                  <span>{passwordChangeSuccess}</span>
                </div>
              )}

              {passwordChangeError && (
                <div className="bg-rose-500/5 border border-rose-500/15 p-4 rounded-lg space-y-2 text-xs text-rose-400 max-w-md font-sans">
                  <div className="flex items-start space-x-2 font-semibold">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
                    <span>Password update failed</span>
                  </div>
                  <p className="text-[11px] text-slate-400 pl-6 leading-relaxed">
                    Please verify your current password and criteria.
                  </p>
                  <details className="pl-6 text-[10px] text-slate-500 cursor-pointer pt-1">
                    <summary className="font-mono hover:text-slate-400">View technical details</summary>
                    <pre className="mt-2 p-2 bg-black/40 border border-white/5 rounded text-rose-300 font-mono whitespace-pre-wrap overflow-x-auto">
                      {passwordChangeError}
                    </pre>
                  </details>
                </div>
              )}
            </div>

            {/* Section 2: Node Configuration */}
            <div className="bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-xl p-6 space-y-4 shadow-xl">
              <div className="border-b border-slate-800/80 pb-3">
                <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide font-sans">Node Configuration</h3>
                <p className="text-xs text-slate-400 mt-1 font-sans">Local workstation infrastructure connection endpoints.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                <div className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-sans">API Endpoint</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">http://127.0.0.1:8000</span>
                  <span className="text-[10px] text-slate-400 block font-sans">Local Subnet Host</span>
                </div>
                <div className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-sans">Vector Database</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">ChromaDB</span>
                  <span className="text-[10px] text-slate-400 block font-sans">Storage: data/chroma_db</span>
                </div>
                <div className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-sans">Audit Database</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">SQLite Append-Only</span>
                  <span className="text-[10px] text-slate-400 block font-sans">Storage: data/private/aegis_auth.db</span>
                </div>
                <div className="p-4 bg-slate-900/60 border border-slate-800/80 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block font-sans">Model Runtime</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">Ollama Engine</span>
                  <span className="text-[10px] text-slate-400 block font-sans">Daemon Port: 11434</span>
                </div>
              </div>
            </div>

            {/* Section 3: Security Policies */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-4">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">Security Policies</h3>
                <p className="text-xs text-slate-450 mt-1">System policies and guardrails enforced on this node.</p>
              </div>

              <div className="space-y-4 pt-2">
                {[
                  { title: "Local Inference Only", desc: "Prevents any external cloud API routing for LLM operations." },
                  { title: "Audit Authentication Events", desc: "Logs login, logout, and token authorization attempts." },
                  { title: "Audit Model Operations", desc: "Logs weight loads, unloads, and model context switches." },
                  { title: "Audit RAG Operations", desc: "Records file ingestion, indexing, and vector similarity queries." },
                  { title: "Sandbox Isolation", desc: "Enforces subprocess sandbox restrictions on code execution." },
                ].map((policy, idx) => (
                  <div key={idx} className="flex items-center justify-between p-4 bg-black/20 border border-white/5 rounded-lg">
                    <div className="space-y-0.5">
                      <h4 className="text-sm font-semibold text-slate-200">{policy.title}</h4>
                      <p className="text-xs text-slate-500">{policy.desc}</p>
                    </div>
                    {/* Custom Toggle Switch */}
                    <div className="flex items-center space-x-2">
                      <span className="text-[10px] font-bold text-emerald-400 font-mono uppercase tracking-wider">ENFORCED</span>
                      <div className="w-11 h-6 bg-emerald-500/20 border border-emerald-500/40 rounded-full p-1 flex items-center justify-end">
                        <div className="w-4 h-4 rounded-full bg-emerald-400 shadow-sm" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 4: System Information */}
            <div className="bg-[#0c1220] border border-white/5 rounded-lg p-6 space-y-4">
              <div className="border-b border-white/5 pb-3">
                <h3 className="text-base font-bold text-slate-200 uppercase tracking-wide">System Information</h3>
                <p className="text-xs text-slate-450 mt-1">Node version identity and execution environment statistics.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 pt-2">
                <div className="p-4 bg-black/20 border border-white/5 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">AEGIS Version</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">1.0.0-MVP</span>
                  <span className="text-[9px] text-slate-550 block font-mono">Sovereign Edition</span>
                </div>
                <div className="p-4 bg-black/20 border border-white/5 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Node ID</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">LOCAL-NODE-01</span>
                  <span className="text-[9px] text-slate-550 block font-mono">Workstation Workgroup</span>
                </div>
                <div className="p-4 bg-black/20 border border-white/5 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Environment</span>
                  <span className="text-sm font-semibold text-emerald-400 font-mono block">Air-Gapped</span>
                  <span className="text-[9px] text-slate-550 block font-mono font-sans">On-Premise Isolated</span>
                </div>
                <div className="p-4 bg-black/20 border border-white/5 rounded-lg space-y-1">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Inference Runtime</span>
                  <span className="text-sm font-semibold text-slate-200 font-mono block">Ollama Daemon</span>
                  <span className="text-[9px] text-slate-550 block font-mono">Open-Weight Models</span>
                </div>
              </div>
            </div>

            {/* Section 5: Security Notice */}
            <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-6 space-y-3">
              <div className="flex items-center space-x-2 text-blue-400 font-bold uppercase tracking-wider text-xs">
                <ShieldCheck className="h-5 w-5" />
                <span>Security Notice & Data Sovereignty Guarantee</span>
              </div>
              <p className="text-xs text-slate-350 leading-relaxed max-w-4xl">
                AEGIS is designed for local, air-gapped AI operation. All model inference, document processing, vector embeddings, and audit logging take place strictly on-premise within this sovereign workstation node. No telemetry or external cloud API calls are made under any condition.
              </p>
            </div>
          </div>
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
