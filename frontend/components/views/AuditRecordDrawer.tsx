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
  Layers
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
  MODEL_LOAD: "Open-weight model loaded into local compute runtime.",
  MODEL_UNLOAD: "Model released and VRAM deallocated.",
  MODEL_SWITCH: "Dynamic local model switch executed.",
  VERIFICATION: "Grounding and anti-hallucination verification evaluated.",
  USER_PROVISIONED: "User account provisioned into authoritative auth registry.",
  USER_CREATED: "User credentials and RBAC role created in SQLite database.",
  AUTHORIZATION_DENIED: "Action blocked by Role-Based Access Control policy.",
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

  const isSuccess = log.status === "success";
  const actionDescription = ACTION_DESCRIPTIONS[log.action];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={typeof window !== "undefined" && window.innerWidth < 768 ? "100%" : 780}
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
            Immutable SQLite Ledger Record
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

        {/* Section 1: Event Details Grid */}
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
            <span>Execution & Routing Context</span>
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
                  Request ID
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

        {/* Section 4: Execution Output Details (if present) */}
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

        {/* Section 5: Record Metadata */}
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-400 border-b border-white/5 pb-1.5">
            <div className="flex items-center gap-2">
              <FileText className="h-3.5 w-3.5 text-cyan-400" />
              <span>Record Metadata Payload</span>
            </div>
            {log.metadata_json && (
              <Button
                type="text"
                size="small"
                onClick={() => copyToClipboard(log.metadata_json || "", "metadata")}
                icon={copiedField === "metadata" ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3 text-slate-400" />}
                className="text-[10px] text-slate-400 hover:text-slate-200 h-6 px-1.5"
              >
                {copiedField === "metadata" ? "Copied" : "Copy JSON"}
              </Button>
            )}
          </div>
          {log.metadata_json ? (
            <pre className="p-3.5 bg-[#05070c] border border-white/10 rounded-lg text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[220px]">
              {JSON.stringify(parsedMetadata, null, 2)}
            </pre>
          ) : (
            <div className="p-3.5 rounded-lg bg-[#0c1220] border border-white/5 text-xs text-slate-500 italic">
              No structured metadata payload recorded for this event.
            </div>
          )}
        </div>

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
