import React from "react";
import { Badge, Tag } from "antd";
export type StatusType = "healthy" | "online" | "offline" | "warning" | "error" | "active" | "inactive" | "processing" | "loading";
export default function StatusBadge({ status, label }: { status: StatusType | string; label?: string }) {
  const value = (status || "unknown").toLowerCase();
  const color = ["healthy", "online", "active", "ready", "enforced", "protected"].includes(value) ? "success" : ["offline", "inactive", "error", "failed"].includes(value) ? "error" : ["warning", "degraded"].includes(value) ? "warning" : ["processing", "loading", "air-gapped", "local"].includes(value) ? "processing" : "default";
  return <Tag color={color}><Badge status={color as "success" | "error" | "warning" | "processing" | "default"} /> {label || status}</Tag>;
}
