import React from "react";

export type StatusType = 
  | "healthy" 
  | "online" 
  | "offline" 
  | "warning" 
  | "error" 
  | "active" 
  | "inactive" 
  | "processing" 
  | "loading";

interface StatusBadgeProps {
  status: StatusType | string;
  label?: string;
}

export default function StatusBadge({ status, label }: StatusBadgeProps) {
  const normStatus = (status || "").toLowerCase();
  let colorClasses = "bg-slate-500/10 text-slate-300 border-slate-700/50";
  let dotColor = "bg-slate-400";
  let animate = false;

  switch (normStatus) {
    case "healthy":
    case "online":
    case "active":
    case "ready":
    case "enforced":
    case "protected":
      colorClasses = "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
      dotColor = "bg-emerald-400";
      break;
    case "offline":
    case "inactive":
    case "error":
    case "failed":
      colorClasses = "bg-rose-500/10 text-rose-400 border-rose-500/30";
      dotColor = "bg-rose-400";
      break;
    case "warning":
    case "degraded":
      colorClasses = "bg-amber-500/10 text-amber-300 border-amber-500/30";
      dotColor = "bg-amber-400";
      break;
    case "processing":
    case "loading":
    case "air-gapped":
    case "local":
      colorClasses = "bg-blue-500/10 text-blue-300 border-blue-500/30";
      dotColor = "bg-blue-400";
      if (normStatus === "processing" || normStatus === "loading") animate = true;
      break;
    case "unavailable":
    case "not reported":
    case "unknown":
      colorClasses = "bg-slate-800/60 text-slate-400 border-slate-700/40";
      dotColor = "bg-slate-500";
      break;
    default:
      break;
  }

  const finalLabel = label || status;

  return (
    <span className={`inline-flex items-center space-x-2 px-2.5 py-1 rounded-md text-[11px] font-semibold border font-sans uppercase tracking-wider ${colorClasses}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor} ${animate ? "animate-pulse" : ""}`} />
      <span>{finalLabel}</span>
    </span>
  );
}
