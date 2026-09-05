"use client";
import React, { useState } from "react";
import { Drawer, Tag, Button, Tooltip } from "antd";
import { 
  CheckCircle2, 
  XCircle, 
  Copy, 
  Check, 
  ShieldCheck, 
  Clock, 
  User, 
  Cpu, 
  FileText, 
  Terminal, 
  Hash, 
  Layers,
  Lock,
  Bot,
  FileCode,
  AlertTriangle,
  FileCheck
} from "lucide-react";
import { AuditLog } from "../../lib/api/audit";

interface AuditRecordDrawerProps {
  log: AuditLog | null;
  open: boolean;
  onClose: () => void;
}

const ACTION_DESCRIPTIONS: Record<string, string> = {
  LOGIN_SUCCESS: "Authenticated operator session established successfully.",
  LOGIN_FAILED: "Authentication attempt rejected due to invalid credentials.",
  AUTH_LOGIN: "Authentication attempt initiated.",
  AUTH_LOGOUT: "Operator session terminated securely.",
  AUTH_CHANGE_PASSWORD: "User password updated with secure cryptographic hashing.",
  DOCUMENT_UPLOAD_STARTED: "Document upload initiated to sovereign storage.",
  DOCUMENT_UPLOAD_COMPLETED: "Document upload completed and staged for ingestion.",
  DOCUMENT_INGEST: "Document text extraction and semantic chunking completed.",
  DOCUMENT_INDEX_STARTED: "Vector embedding generation and indexing initiated.",
  DOCUMENT_INDEX_COMPLETED: "Document indexed into local ChromaDB vector repository.",
  DOCUMENT_INDEX_FAILED: "Document indexing encountered an unrecoverable parsing error.",
  DOCUMENT_DUPLICATE_DETECTED: "Content deduplication check identified an identical document.",
  RAG_QUERY: "Grounded query processed against confidential organizational knowledge.",
  RAG_QUERY_STARTED: "Grounded semantic retrieval and query pipeline started.",
  RAG_QUERY_COMPLETED: "Grounded question-answering completed with citation evidence.",
  RAG_QUERY_FAILED: "RAG query pipeline execution failed.",
  RAG_SEARCH: "Vector similarity search executed in local ChromaDB.",
  DOCUMENT_GENERATION: "Physical document generation pipeline executed.",
  DOCUMENT_GENERATION_STARTED: "Whole-document analysis and report synthesis initiated.",
  DOCUMENT_GENERATED: "Physical report compiled and validated on local storage.",
  DOCUMENT_GENERATION_FAILED: "Document report generation failed during rendering.",
  DOCUMENT_DOWNLOADED: "Generated report streamed to authorized client via REST API.",
  DOCUMENT_DOWNLOAD_STARTED: "Document download request authorized and streaming started.",
  DOCUMENT_DOWNLOAD_COMPLETED: "Document binary stream transmitted successfully.",
  SANDBOX_EXECUTION: "Isolated subprocess code sandbox execution completed.",
  SANDBOX_EXECUTION_STARTED: "Isolated code sandbox execution initiated in restricted subprocess.",
  SANDBOX_EXECUTION_COMPLETED: "Sandbox execution completed successfully with exit code 0.",
  SANDBOX_EXECUTION_FAILED: "Sandbox execution terminated with error or non-zero exit code.",
  SANDBOX_FILE_CREATED: "New file written into isolated sandbox storage.",
  MODEL_LOAD: "Open-weight model loaded into local compute runtime.",
  MODEL_UNLOAD: "Model released and VRAM deallocated.",
  MODEL_SWITCH: "Dynamic local model switch executed.",
  MODEL_INFERENCE: "Open-weight multimodal model inference executed locally on-premise.",
  MODEL_ROUTED: "Task routed to optimal open-weight model based on required capabilities.",
  VERIFICATION: "Grounding and anti-hallucination verification evaluated.",
  USER_PROVISIONED: "User account provisioned into authoritative auth registry.",
  USER_CREATED: "User credentials and RBAC role created in SQLite database.",
  AUTHORIZATION_DENIED: "Action blocked by Role-Based Access Control policy.",
  AUTHORIZATION_FAILURE: "Access request denied due to insufficient permissions or ownership mismatch.",
  DOCUMENT_ACCESS_DENIED: "Confidential document access denied by sovereign ACL policy.",
};

export default function AuditRecordDrawer({ log, open, onClose }: AuditRecordDrawerProps) {
  const [copiedField, setCopiedField] = useState<string | null>(null);

  if (!log) return null;

  const copyToClipboard = (text: string, fieldName: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  let parsedMetadata: Record<string, unknown> = {};
  if (log.metadata_json) {
    try {
      parsedMetadata = JSON.parse(log.metadata_json) as Record<string, unknown>;
    } catch {
      parsedMetadata = {};
    }
  }

  const hasMetadata = Object.keys(parsedMetadata).length > 0;
  const isSuccess = log.status === "success";
  const actionDescription = ACTION_DESCRIPTIONS[log.action];

  // Forensic classification helpers
  const isDocGen = log.action.includes("DOCUMENT_GENERAT") || parsedMetadata["document_id"] != null;
  const isDocDownload = log.action.includes("DOCUMENT_DOWNLOAD");
  const isDuplicate = log.action.includes("DUPLICATE") || parsedMetadata["content_hash"] != null;
  const isModelInference = log.action.includes("MODEL_INFERENCE") || parsedMetadata["model"] != null;
  const isSandbox = log.action.includes("SANDBOX") || parsedMetadata["run_id"] != null;
  const isAuthFailure = log.action.includes("AUTHORIZATION") || log.action.includes("ACCESS_DENIED") || parsedMetadata["result"] === "denied";

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      size={typeof window !== "undefined" && window.innerWidth < 768 ? "100%" : 800}
      closable={true}
      title={
        <div className="flex items-center justify-between gap-3 pr-2">
          <div className="flex items-center gap-2.5">
            <span className="flex items-center justify-center h-7 w-7 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <ShieldCheck className="h-4 w-4" />
            </span>
            <span className="text-base font-bold text-slate-100 tracking-wide">
              Audit Record #{log.id}
            </span>
          </div>
          <Tag
            color={isSuccess ? "success" : "error"}
            className="px-2.5 py-0.5 text-xs font-bold tracking-wider uppercase border rounded"
          >
            {isSuccess ? "● SUCCESS" : "● FAILURE"}
          </Tag>
        </div>
      }
      styles={{
        wrapper: { maxWidth: "100vw" },
        header: {
          backgroundColor: "#0c1220",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          padding: "16px 24px",
        },
        body: {
          backgroundColor: "#080c14",
          color: "#f1f5f9",
          padding: "24px",
          fontFamily: "inherit",
        },
        footer: {
          backgroundColor: "#0c1220",
          borderTop: "1px solid rgba(255, 255, 255, 0.08)",
          padding: "12px 24px",
        },
      }}
      footer={
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-450 font-mono">
            Immutable SQLite Ledger Record • Confidential Forensic View
          </span>
          <Button
            type="primary"
            onClick={onClose}
            className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-5"
          >
            Close
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        {/* Banner Section */}
        <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 to-[#0d1627] border border-white/10 shadow-lg space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-450">
                Action Type
              </span>
              <span className="px-2.5 py-1 rounded bg-blue-500/15 border border-blue-500/30 text-blue-400 font-mono text-sm font-bold">
                {log.action}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
              <Clock className="h-3.5 w-3.5 text-slate-450" />
              <span>{new Date(log.timestamp).toUTCString()}</span>
            </div>
          </div>
          {actionDescription && (
            <p className="text-sm text-slate-300 leading-relaxed pt-1">
              {actionDescription}
            </p>
          )}
        </div>

        {/* Section 1: Event Specification Grid */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
            <Layers className="h-3.5 w-3.5 text-blue-400" />
            <span>Event Specification</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Event ID
              </div>
              <div className="text-sm font-bold text-slate-100 font-mono">
                #{log.id}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Execution Status
              </div>
              <div className="flex items-center gap-1.5 text-sm font-bold font-mono">
                {isSuccess ? (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    <span className="text-emerald-400">SUCCESS</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-4 w-4 text-rose-400" />
                    <span className="text-rose-400">FAILURE</span>
                  </>
                )}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Recorded Timestamp
              </div>
              <div className="text-xs font-mono text-slate-200">
                {new Date(log.timestamp).toLocaleString()}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Execution Duration
              </div>
              <div className="text-sm font-mono text-slate-200">
                {log.duration_ms != null ? `${log.duration_ms} ms` : "Not recorded"}
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Actor Identity Grid */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
            <User className="h-3.5 w-3.5 text-indigo-400" />
            <span>Actor & Security Identity</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Username / Operator
              </div>
              <div className="text-sm font-bold text-slate-100">
                {log.username || "System Process"}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                User ID
              </div>
              <div className="text-sm font-mono text-slate-200">
                {log.user_id != null ? `#${log.user_id}` : "System"}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Assigned Role
              </div>
              <div className="text-sm font-mono text-slate-200 uppercase font-semibold">
                {log.role || "SYSTEM"}
              </div>
            </div>
          </div>
        </div>

        {/* Section 3: Execution Context */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
            <Cpu className="h-3.5 w-3.5 text-emerald-400" />
            <span>Execution & Correlation Context</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Component Module
              </div>
              <div className="text-sm font-mono text-slate-200">
                {log.component}
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                Target Resource
              </div>
              <div className="text-sm font-mono text-slate-200 truncate" title={log.resource || "None"}>
                {log.resource || "None"}
              </div>
            </div>

            <div className="md:col-span-2 p-3.5 rounded-lg bg-[#0c1220] border border-white/5 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                  Request / Correlation ID
                </span>
                {log.request_id && (
                  <Button
                    type="text"
                    size="small"
                    onClick={() => copyToClipboard(log.request_id || "", "request_id")}
                    icon={copiedField === "request_id" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-slate-400" />}
                    className="text-[10px] text-slate-400 hover:text-slate-200 h-6 px-1.5"
                  >
                    {copiedField === "request_id" ? "Copied" : "Copy"}
                  </Button>
                )}
              </div>
              <div className="text-xs font-mono text-slate-300 select-all break-all bg-black/40 p-2 rounded border border-white/5">
                {log.request_id || "Not recorded"}
              </div>
            </div>
          </div>
        </div>

        {/* Section 4: Structured Forensic Details */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
            <div className="flex items-center gap-2">
              <FileCheck className="h-3.5 w-3.5 text-cyan-400" />
              <span>Forensic Audit Details</span>
            </div>
            {hasMetadata && (
              <Tag color="blue" className="text-[10px] uppercase font-mono">
                {Object.keys(parsedMetadata).length} attributes
              </Tag>
            )}
          </div>

          {!hasMetadata ? (
            <div className="p-4 rounded-lg bg-[#0c1220] border border-white/5 text-sm text-slate-400 italic">
              No additional details recorded.
            </div>
          ) : (
            <div className="space-y-3">
              {/* Highlight Cards for Common Forensic Event Types */}
              {isDocGen && (
                <div className="p-3.5 rounded-lg bg-blue-950/20 border border-blue-500/20 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase text-blue-400">
                    <FileText className="h-3.5 w-3.5" />
                    <span>Document Generation Intelligence</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                    {parsedMetadata["document_id"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Document ID:</span>
                        <span className="font-mono text-slate-200 font-semibold">{String(parsedMetadata["document_id"])}</span>
                      </div>
                    )}
                    {parsedMetadata["artifact_id"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Artifact ID:</span>
                        <span className="font-mono text-slate-200 font-semibold">{String(parsedMetadata["artifact_id"])}</span>
                      </div>
                    )}
                    {(parsedMetadata["output_format"] != null || parsedMetadata["format"] != null) && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Format:</span>
                        <Tag color="cyan" className="font-mono font-bold uppercase text-[10px] mt-0.5">
                          {String(parsedMetadata["output_format"] || parsedMetadata["format"])}
                        </Tag>
                      </div>
                    )}
                    {parsedMetadata["file_size"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">File Size:</span>
                        <span className="font-mono text-slate-200">{Number(parsedMetadata["file_size"]).toLocaleString()} bytes</span>
                      </div>
                    )}
                    {parsedMetadata["source_count"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Sources Cited:</span>
                        <span className="font-mono text-slate-200">{String(parsedMetadata["source_count"])} sources</span>
                      </div>
                    )}
                    {parsedMetadata["conversation_id"] != null && String(parsedMetadata["conversation_id"]) !== "" && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Conversation ID:</span>
                        <span className="font-mono text-slate-200">{String(parsedMetadata["conversation_id"])}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {isDocDownload && (
                <div className="p-3.5 rounded-lg bg-teal-950/20 border border-teal-500/20 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase text-teal-400">
                    <FileCheck className="h-3.5 w-3.5" />
                    <span>Download Operation Details</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                    {parsedMetadata["artifact_id"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Artifact ID:</span>
                        <span className="font-mono text-slate-200 font-semibold">{String(parsedMetadata["artifact_id"])}</span>
                      </div>
                    )}
                    {(parsedMetadata["output_format"] != null || parsedMetadata["format"] != null) && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Format:</span>
                        <Tag color="geekblue" className="font-mono uppercase text-[10px] mt-0.5">
                          {String(parsedMetadata["output_format"] || parsedMetadata["format"])}
                        </Tag>
                      </div>
                    )}
                    {parsedMetadata["file_size"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Transmitted Size:</span>
                        <span className="font-mono text-slate-200">{Number(parsedMetadata["file_size"]).toLocaleString()} bytes</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {isDuplicate && (
                <div className="p-3.5 rounded-lg bg-amber-950/20 border border-amber-500/20 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase text-amber-400">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    <span>Deduplication & Cryptographic Verification</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    {parsedMetadata["content_hash"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Content SHA-256 Hash:</span>
                        <div className="font-mono text-xs text-amber-300 select-all break-all bg-black/40 p-1.5 rounded border border-amber-500/10">
                          {String(parsedMetadata["content_hash"])}
                        </div>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-2 pt-1">
                      {parsedMetadata["result"] != null && (
                        <div>
                          <span className="text-slate-400 block text-[10px]">Deduplication Result:</span>
                          <Tag color="warning" className="font-mono text-[10px]">{String(parsedMetadata["result"])}</Tag>
                        </div>
                      )}
                      {(parsedMetadata["canonical_document_id"] != null || parsedMetadata["document_id"] != null) && (
                        <div>
                          <span className="text-slate-400 block text-[10px]">Canonical Document:</span>
                          <span className="font-mono text-slate-200">{String(parsedMetadata["canonical_document_id"] || parsedMetadata["document_id"])}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {isModelInference && (
                <div className="p-3.5 rounded-lg bg-purple-950/20 border border-purple-500/20 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase text-purple-400">
                    <Bot className="h-3.5 w-3.5" />
                    <span>Model Inference Telemetry</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                    {(parsedMetadata["model"] != null || parsedMetadata["model_id"] != null) && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Model:</span>
                        <Tag color="purple" className="font-mono font-bold text-[10px] mt-0.5">
                          {String(parsedMetadata["model"] || parsedMetadata["model_id"])}
                        </Tag>
                      </div>
                    )}
                    {parsedMetadata["task_type"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Task Type:</span>
                        <span className="font-mono text-slate-200">{String(parsedMetadata["task_type"])}</span>
                      </div>
                    )}
                    {parsedMetadata["duration_ms"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Latency:</span>
                        <span className="font-mono text-slate-200">{String(parsedMetadata["duration_ms"])} ms</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {isSandbox && (
                <div className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-500/20 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase text-emerald-400">
                    <FileCode className="h-3.5 w-3.5" />
                    <span>Sandbox Subprocess Telemetry</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    {(parsedMetadata["run_id"] != null || parsedMetadata["execution_id"] != null) && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Run ID:</span>
                        <span className="font-mono text-slate-200 font-semibold">{String(parsedMetadata["run_id"] || parsedMetadata["execution_id"])}</span>
                      </div>
                    )}
                    {parsedMetadata["exit_code"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Exit Code:</span>
                        <Tag color={parsedMetadata["exit_code"] === 0 ? "success" : "error"} className="font-mono text-[10px]">
                          {String(parsedMetadata["exit_code"])}
                        </Tag>
                      </div>
                    )}
                    {parsedMetadata["duration_ms"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Duration:</span>
                        <span className="font-mono text-slate-200">{String(parsedMetadata["duration_ms"])} ms</span>
                      </div>
                    )}
                    {parsedMetadata["result"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Result:</span>
                        <Tag color={parsedMetadata["result"] === "success" ? "success" : "error"} className="font-mono uppercase text-[10px]">
                          {String(parsedMetadata["result"])}
                        </Tag>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {isAuthFailure && (
                <div className="p-3.5 rounded-lg bg-rose-950/20 border border-rose-500/20 space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase text-rose-400">
                    <Lock className="h-3.5 w-3.5" />
                    <span>Security Authorization Failure</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                    {parsedMetadata["resource_type"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Resource Type:</span>
                        <span className="font-mono text-slate-200 font-semibold">{String(parsedMetadata["resource_type"])}</span>
                      </div>
                    )}
                    {parsedMetadata["resource_id"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Resource ID:</span>
                        <span className="font-mono text-slate-200">{String(parsedMetadata["resource_id"])}</span>
                      </div>
                    )}
                    {parsedMetadata["action"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Attempted Action:</span>
                        <Tag color="volcano" className="font-mono uppercase text-[10px]">{String(parsedMetadata["action"])}</Tag>
                      </div>
                    )}
                    {parsedMetadata["result"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Result:</span>
                        <Tag color="error" className="font-mono uppercase text-[10px]">{String(parsedMetadata["result"])}</Tag>
                      </div>
                    )}
                    {parsedMetadata["reason"] != null && (
                      <div>
                        <span className="text-slate-400 block text-[10px]">Denial Reason:</span>
                        <span className="font-mono text-rose-300">{String(parsedMetadata["reason"])}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Complete Structured Details Table / JSON */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                    Structured Attributes Payload
                  </span>
                  {log.metadata_json && (
                    <Button
                      type="text"
                      size="small"
                      onClick={() => copyToClipboard(log.metadata_json || "", "metadata")}
                      icon={copiedField === "metadata" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-slate-400" />}
                      className="text-[10px] text-slate-400 hover:text-slate-200 h-6 px-1.5"
                    >
                      {copiedField === "metadata" ? "Copied JSON" : "Copy JSON"}
                    </Button>
                  )}
                </div>
                <pre className="p-3.5 bg-[#05070c] border border-white/10 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[220px]">
                  {JSON.stringify(parsedMetadata, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Section 5: Execution Output Details (stdout/stderr if present) */}
        {(["stdout", "stderr", "error"] as const).some((k) => parsedMetadata[k] != null) && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
              <Terminal className="h-3.5 w-3.5 text-amber-400" />
              <span>Process Execution Output</span>
            </div>
            {(["stdout", "stderr", "error"] as const).map((key) => {
              if (parsedMetadata[key] == null) return null;
              return (
                <div key={key} className="space-y-1">
                  <span className="text-[11px] font-semibold uppercase text-slate-450 font-mono">
                    {key}
                  </span>
                  <pre className="p-3 bg-[#05070c] border border-white/10 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[180px]">
                    {String(parsedMetadata[key])}
                  </pre>
                </div>
              );
            })}
          </div>
        )}

        {/* Section 6: Cryptographic Integrity */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
            <div className="flex items-center gap-2">
              <Hash className="h-3.5 w-3.5 text-purple-400" />
              <span>Cryptographic Chain Integrity</span>
            </div>
            {log.entry_hash && (
              <span className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> HMAC-SHA256 Linked
              </span>
            )}
          </div>
          {log.entry_hash ? (
            <div className="space-y-3">
              <div className="p-3 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                    Previous Record Hash
                  </span>
                  <Tooltip title="Copy Previous Hash">
                    <Button
                      type="text"
                      size="small"
                      onClick={() => copyToClipboard(log.previous_hash || "", "prev_hash")}
                      icon={copiedField === "prev_hash" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-slate-400" />}
                      className="text-[10px] text-slate-400 hover:text-slate-200 h-6 px-1.5"
                    />
                  </Tooltip>
                </div>
                <div className="text-xs font-mono text-slate-300 select-all break-all bg-black/40 p-2 rounded border border-white/5">
                  {log.previous_hash || "GENESIS_ROOT_HASH"}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-[#0c1220] border border-white/5 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-450">
                    Entry Hash (HMAC-SHA256)
                  </span>
                  <Tooltip title="Copy Entry Hash">
                    <Button
                      type="text"
                      size="small"
                      onClick={() => copyToClipboard(log.entry_hash || "", "entry_hash")}
                      icon={copiedField === "entry_hash" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-slate-400" />}
                      className="text-[10px] text-slate-400 hover:text-slate-200 h-6 px-1.5"
                    />
                  </Tooltip>
                </div>
                <div className="text-xs font-mono text-emerald-400 select-all break-all bg-black/40 p-2 rounded border border-white/5 font-bold">
                  {log.entry_hash}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 text-xs text-slate-500 italic">
              Cryptographic hash linkage not available on this record.
            </div>
          )}
        </div>
      </div>
    </Drawer>
  );
}
