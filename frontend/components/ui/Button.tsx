import React from "react";

export type ButtonVariant = "primary" | "secondary" | "destructive" | "ghost" | "icon";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: React.ReactNode;
  loading?: boolean;
}

export default function Button({ 
  children, 
  variant = "secondary", 
  icon, 
  loading, 
  className = "", 
  disabled, 
  ...props 
}: ButtonProps) {
  let baseClasses = "inline-flex items-center justify-center rounded-lg text-xs font-semibold tracking-wide font-sans transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed select-none focus:outline-none focus:ring-2 focus:ring-blue-500/40";
  let variantClasses = "";
  let sizeClasses = "h-9 px-4 py-2";

  switch (variant) {
    case "primary":
      variantClasses = "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white border border-blue-500/30 shadow-lg shadow-blue-600/20 active:opacity-90";
      break;
    case "destructive":
      variantClasses = "bg-rose-500/15 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 active:bg-rose-700";
      break;
    case "ghost":
      variantClasses = "hover:bg-slate-800/60 text-slate-300 hover:text-white border border-transparent";
      break;
    case "icon":
      variantClasses = "hover:bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-transparent";
      sizeClasses = "h-9 w-9 shrink-0";
      break;
    case "secondary":
    default:
      variantClasses = "bg-slate-800/60 hover:bg-slate-700/80 text-slate-200 border border-slate-700/60 active:bg-slate-800";
      break;
  }

  return (
    <button
      disabled={disabled || loading}
      className={`${baseClasses} ${variantClasses} ${sizeClasses} ${className}`}
      {...props}
    >
      {loading ? (
        <span className="h-3.5 w-3.5 border-2 border-slate-300 border-t-transparent rounded-full animate-spin mr-2" />
      ) : icon ? (
        <span className="mr-2 inline-flex items-center">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
