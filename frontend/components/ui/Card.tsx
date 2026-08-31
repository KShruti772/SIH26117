import React from "react";
import { Alert, Card as AntCard, Empty, Spin } from "antd";
interface CardProps { title?: string; description?: string; icon?: React.ReactNode; status?: React.ReactNode; footer?: React.ReactNode; loading?: boolean; empty?: boolean; emptyMessage?: string; error?: string | null; children?: React.ReactNode; className?: string; }
export default function Card({ title, description, icon, status, footer, loading, empty, emptyMessage = "No records found.", error, children, className }: CardProps) {
  const heading = title ? <div><span className="inline-flex items-center gap-2">{icon}{title}</span>{description && <div className="mt-1 text-xs text-slate-400 font-normal">{description}</div>}</div> : undefined;
  return <AntCard className={`aegis-panel-card ${className || ""}`} title={heading} extra={status} actions={footer ? [footer] : undefined}>{loading ? <div className="py-8 text-center"><Spin tip="Loading data…" /></div> : error ? <Alert type="error" showIcon message="Error occurred" description={error} /> : empty ? <Empty description={emptyMessage} /> : children}</AntCard>;
}
