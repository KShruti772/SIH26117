"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Clock,
  Cpu,
  ShieldCheck,
  ChevronDown,
  ChevronRight,
  Terminal,
  Database,
  Search,
  FileCode,
  FileText,
  Eye,
  PauseCircle,
  XCircle,
  Radio
} from "lucide-react";
import type { ExecutionEvent, PlanStep, ExecutionPlan } from "../../lib/api/chat";

interface LiveExecutionPanelProps {
  status: "sending" | "success" | "error";
  executionId?: string;
  executionEvents?: ExecutionEvent[];
  plan?: ExecutionPlan;
  durationMs?: number;
  modelId?: string;
  defaultExpanded?: boolean;
  className?: string;
}

export function formatEventTypeLabel(eventType: string): string {
  switch (eventType) {
    case "REQUEST_RECEIVED":
      return "Request Received";
    case "PLANNING_STARTED":
      return "Analyzing Intent";
    case "PLAN_CREATED":
      return "Plan Initialized";
    case "STEP_STARTED":
      return "Executing Step";
    case "STEP_COMPLETED":
      return "Step Complete";
    case "STEP_FAILED":
      return "Step Failed";
    case "RAG_STARTED":
      return "Querying Local RAG";
    case "RAG_COMPLETED":
      return "RAG Context Ready";
    case "MODEL_INFERENCE_STARTED":
      return "Local Model Inference";
    case "MODEL_INFERENCE_COMPLETED":
      return "Inference Complete";
    case "SANDBOX_EXECUTION_STARTED":
      return "Running Isolated Sandbox";
    case "SANDBOX_EXECUTION_COMPLETED":
      return "Sandbox Complete";
    case "DOCUMENT_GENERATION_STARTED":
      return "Generating Document";
    case "DOCUMENT_GENERATED":
      return "Document Ready";
    case "VISION_ANALYSIS_STARTED":
      return "Analyzing Image/OCR";
    case "VISION_ANALYSIS_COMPLETED":
      return "Vision Complete";
    case "VERIFICATION_STARTED":
      return "Grounding Verification";
    case "VERIFICATION_COMPLETED":
      return "Verification Complete";
    case "REPLAN_STARTED":
      return "Auto-Replanning";
    case "WAITING_FOR_HUMAN":
      return "Awaiting Approval";
    case "EXECUTION_COMPLETED":
      return "Execution Finished";
    case "EXECUTION_FAILED":
      return "Execution Failed";
    default:
      return eventType.replace(/_/g, " ");
  }
}

function getEventIcon(eventType: string) {
  if (eventType.startsWith("RAG")) {
    return <Search className="h-3 w-3 text-cyan-400 shrink-0" />;
  }
  if (eventType.startsWith("MODEL")) {
    return <Cpu className="h-3 w-3 text-blue-400 shrink-0" />;
  }
  if (eventType.startsWith("SANDBOX")) {
    return <Terminal className="h-3 w-3 text-amber-400 shrink-0" />;
  }
  if (eventType.startsWith("DOCUMENT")) {
    return <FileText className="h-3 w-3 text-purple-400 shrink-0" />;
  }
  if (eventType.startsWith("VISION")) {
    return <Eye className="h-3 w-3 text-pink-400 shrink-0" />;
  }
  if (eventType.startsWith("VERIFICATION")) {
    return <ShieldCheck className="h-3 w-3 text-emerald-400 shrink-0" />;
  }
  if (eventType.startsWith("REPLAN")) {
    return <RotateCcw className="h-3 w-3 text-amber-400 shrink-0" />;
  }
  if (eventType === "WAITING_FOR_HUMAN") {
    return <PauseCircle className="h-3 w-3 text-indigo-400 shrink-0" />;
  }
  if (eventType.includes("FAILED")) {
    return <XCircle className="h-3 w-3 text-rose-400 shrink-0" />;
  }
  return <Radio className="h-3 w-3 text-slate-400 shrink-0" />;
}

export default function LiveExecutionPanel({
  status,
  executionId,
  executionEvents = [],
  plan,
  durationMs,
  modelId,
  defaultExpanded,
  className = ""
}: LiveExecutionPanelProps) {
  const isRunning = status === "sending";
  const [isExpanded, setIsExpanded] = useState<boolean>(defaultExpanded ?? isRunning);
  const [elapsedMs, setElapsedMs] = useState<number>(0);
  const [showEventLog, setShowEventLog] = useState<boolean>(false);

  // Live timer while running
  useEffect(() => {
    if (!isRunning) return;
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsedMs(Date.now() - start);
    }, 100);
    return () => clearInterval(interval);
  }, [isRunning]);

  const latestEvent = executionEvents.length > 0 ? executionEvents[executionEvents.length - 1] : null;
  const isReplanning = executionEvents.some(
    (e) => e.event_type === "REPLAN_STARTED" || (e.metadata && e.metadata.is_replan)
  );
  const isWaitingHuman = latestEvent?.event_type === "WAITING_FOR_HUMAN";
  const isFailed = status === "error" || latestEvent?.event_type === "EXECUTION_FAILED";
  const isSuccess = status === "success" && !isFailed;

  const displayExecutionId = executionId || latestEvent?.execution_id || "EXE-SOV-NODE";
  const displayDuration = durationMs !== undefined ? `${(durationMs / 1000).toFixed(2)}s` : `${(elapsedMs / 1000).toFixed(1)}s`;

  // Determine current active pipeline label
  let activeStatusLabel = "Initializing";
  if (isRunning) {
    if (isWaitingHuman) activeStatusLabel = "Waiting for Human Approval";
    else if (isReplanning) activeStatusLabel = "Auto-Replanning";
    else if (latestEvent) activeStatusLabel = formatEventTypeLabel(latestEvent.event_type);
    else activeStatusLabel = "Executing Agent Workflow";
  } else if (isFailed) {
    activeStatusLabel = "Execution Faulted";
  } else {
    activeStatusLabel = "Execution Complete";
  }

  const steps: PlanStep[] = plan?.steps || [];

  return (
    <div
      className={`rounded-xl border transition-all duration-200 overflow-hidden font-sans ${
        isRunning
          ? "bg-slate-950/80 border-blue-500/30 shadow-lg shadow-blue-500/5"
          : isFailed
          ? "bg-[#180a0a]/80 border-rose-500/30"
          : "bg-[#090d16]/70 border-slate-800/80 hover:border-slate-700/80"
      } ${className}`}
      aria-live="polite"
    >
      {/* Header bar */}
      <div className="p-3.5 flex flex-wrap items-center justify-between gap-2.5 border-b border-white/[0.06]">
        <div className="flex items-center space-x-2.5 min-w-0">
          {isRunning ? (
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
            </span>
          ) : isFailed ? (
            <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          )}

          <div className="flex items-center space-x-2 min-w-0">
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wide">
              {isRunning ? (
                <span className="text-blue-400 font-semibold">Running Sovereign Execution</span>
              ) : isFailed ? (
                <span className="text-rose-400 font-semibold">Execution Failed</span>
              ) : (
                <span className="text-emerald-400 font-semibold">Execution Verified</span>
              )}
            </span>
            <span className="text-slate-600">•</span>
            <span className="text-[11px] font-mono text-slate-400 truncate" title={displayExecutionId}>
              {displayExecutionId}
            </span>
          </div>
        </div>

        {/* Badges & Metrics */}
        <div className="flex items-center space-x-2 text-[11px]">
          <span className="hidden sm:inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 font-mono border border-blue-500/20 text-[10px]">
            <ShieldCheck className="h-3 w-3" />
            <span>AIR-GAPPED</span>
          </span>

          {modelId && (
            <span className="hidden md:inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px] border border-slate-700">
              <Cpu className="h-3 w-3 text-slate-400" />
              <span className="truncate max-w-[120px]" title={modelId}>{modelId}</span>
            </span>
          )}

          <span className="flex items-center space-x-1 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 font-mono text-[10px]">
            <Clock className="h-3 w-3 text-slate-400" />
            <span>{displayDuration}</span>
          </span>

          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 text-slate-400 hover:text-slate-200 rounded hover:bg-slate-800/60 transition-colors cursor-pointer"
            aria-label={isExpanded ? "Collapse execution details" : "Expand execution details"}
          >
            {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Active Pipeline Status Banner */}
      <div className="px-3.5 py-2 bg-slate-900/40 flex items-center justify-between text-xs border-b border-white/[0.04]">
        <div className="flex items-center space-x-2 min-w-0">
          <Activity className={`h-3.5 w-3.5 ${isRunning ? "text-blue-400 animate-pulse" : isFailed ? "text-rose-400" : "text-emerald-400"} shrink-0`} />
          <span className="text-slate-300 font-medium truncate">
            {latestEvent?.message || activeStatusLabel}
          </span>
        </div>
        {latestEvent?.step_type && (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800/80 text-slate-300 border border-slate-700/60 shrink-0">
            {latestEvent.step_type}
          </span>
        )}
      </div>

      {/* Expanded Content: Plan Steps Timeline & Event Stream */}
      {isExpanded && (
        <div className="p-3.5 space-y-3.5 text-xs">
          {/* Plan Steps Timeline */}
          {steps.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>Execution Plan Steps ({steps.length})</span>
                {plan?.status && (
                  <span className="text-[10px] text-slate-500 font-mono">STATUS: {plan.status}</span>
                )}
              </div>

              <div className="space-y-1.5">
                {steps.map((step, idx) => {
                  const isStepRunning = step.status === "RUNNING";
                  const isStepComplete = step.status === "COMPLETED";
                  const isStepFailed = step.status === "FAILED";
                  const isStepReplan = step.is_replan || (step.replan_count && step.replan_count > 0);

                  return (
                    <div
                      key={step.step_id || idx}
                      className={`p-2.5 rounded-lg border text-xs transition-all ${
                        isStepRunning
                          ? "bg-blue-950/20 border-blue-500/40 shadow-sm"
                          : isStepFailed
                          ? "bg-rose-950/20 border-rose-500/30"
                          : isStepComplete
                          ? "bg-slate-900/50 border-slate-800/80"
                          : "bg-slate-900/20 border-slate-800/40 text-slate-500"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center space-x-2 min-w-0">
                          <span
                            className={`flex items-center justify-center h-4 w-4 rounded-full text-[10px] font-mono font-bold shrink-0 ${
                              isStepComplete
                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                : isStepFailed
                                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                                : isStepRunning
                                ? "bg-blue-500/20 text-blue-400 border border-blue-500/30 animate-pulse"
                                : "bg-slate-800 text-slate-400 border border-slate-700"
                            }`}
                          >
                            {step.step_id || idx + 1}
                          </span>

                          <span className="font-medium text-slate-200 truncate">
                            {step.description || `Step ${step.step_id || idx + 1}`}
                          </span>

                          {isStepReplan && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30 text-[9px] font-mono shrink-0 flex items-center space-x-0.5">
                              <RotateCcw className="h-2.5 w-2.5" />
                              <span>RE-PLANNED</span>
                            </span>
                          )}
                        </div>

                        <div className="flex items-center space-x-1.5 shrink-0 text-[10px] font-mono">
                          {step.selected_model && (
                            <span className="hidden sm:inline px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/50">
                              {step.selected_model}
                            </span>
                          )}

                          {step.duration_ms !== undefined && (
                            <span className="text-slate-400">
                              {step.duration_ms}ms
                            </span>
                          )}

                          {step.verification_result && (
                            <span
                              className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                step.verification_result === "PASS" || step.verification_result.startsWith("PASS")
                                  ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                                  : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                              }`}
                            >
                              VERIFY: {step.verification_result}
                            </span>
                          )}
                        </div>
                      </div>

                      {step.output_summary && (
                        <div className="mt-1.5 pl-6 text-[11px] text-slate-400 font-sans leading-relaxed">
                          {step.output_summary}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Collapsible Live Operational Event Stream */}
          {executionEvents.length > 0 && (
            <div className="space-y-1.5 pt-1 border-t border-slate-800/60">
              <button
                type="button"
                onClick={() => setShowEventLog(!showEventLog)}
                className="flex items-center space-x-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
              >
                {showEventLog ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                <span>Live Event Stream ({executionEvents.length} events)</span>
              </button>

              {showEventLog && (
                <div className="p-2.5 bg-[#050811] rounded-lg border border-slate-800 font-mono text-[10px] space-y-1 max-h-48 overflow-y-auto">
                  {executionEvents.map((evt, eIdx) => {
                    const timeStr = evt.timestamp ? evt.timestamp.split("T")[1]?.slice(0, 8) || evt.timestamp : "--:--:--";
                    return (
                      <div key={eIdx} className="flex items-start space-x-2 text-slate-400 leading-relaxed">
                        <span className="text-slate-600 shrink-0">{timeStr}</span>
                        <span className="shrink-0">{getEventIcon(evt.event_type)}</span>
                        <span className="font-semibold text-slate-300 shrink-0">[{evt.event_type}]</span>
                        <span className="text-slate-400 truncate">{evt.message || ""}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
