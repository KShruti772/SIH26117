import React from "react";
import { AlertCircle, FileText, Loader2 } from "lucide-react";

interface CardProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  status?: React.ReactNode;
  footer?: React.ReactNode;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  error?: string | null;
  children?: React.ReactNode;
  className?: string;
}

export default function Card({
  title,
  description,
  icon,
  status,
  footer,
  loading,
  empty,
  emptyMessage = "No records found.",
  error,
  children,
  className = ""
}: CardProps) {
  return (
    <div className={`bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-xl flex flex-col font-sans transition-all hover:border-slate-700/80 shadow-xl shadow-black/40 ${className}`}>
      {/* Card Header */}
      {(title || description || icon || status) && (
        <div className="p-5 md:p-6 border-b border-slate-800/80 flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2.5">
              {icon && <span className="text-blue-400 shrink-0">{icon}</span>}
              {title && <h3 className="text-base sm:text-lg font-bold text-slate-100 tracking-wide font-sans">{title}</h3>}
            </div>
            {description && <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">{description}</p>}
          </div>
          {status && <div className="shrink-0">{status}</div>}
        </div>
      )}

      {/* Card Content Body */}
      <div className="flex-1 p-5 md:p-6 relative">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-12 text-center text-xs text-slate-400 space-y-2.5 font-sans">
            <Loader2 className="h-6 w-6 animate-spin text-blue-400" />
            <span className="font-semibold tracking-wide text-xs">Loading data...</span>
          </div>
        ) : error ? (
          <div className="flex items-start space-x-3 p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-300 text-xs font-sans">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold block tracking-wide">Error Occurred</span>
              <span>{error}</span>
            </div>
          </div>
        ) : empty ? (
          <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400 space-y-2.5 font-sans">
            <FileText className="h-8 w-8 text-slate-600 opacity-40" />
            <span className="text-xs font-bold tracking-wide uppercase text-slate-300">No Data Available</span>
            <p className="text-xs text-slate-500 max-w-xs">{emptyMessage}</p>
          </div>
        ) : (
          children
        )}
      </div>

      {/* Card Footer */}
      {footer && (
        <div className="px-5 md:px-6 py-3.5 bg-black/20 border-t border-slate-800/80 rounded-b-xl text-xs flex items-center justify-between font-sans">
          {footer}
        </div>
      )}
    </div>
  );
}
