"use client";
import React, { useEffect, useState } from "react";
import { Avatar, Badge, Breadcrumb, Button, Space, Tag, Typography } from "antd";
import { LogoutOutlined, MenuOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useAuth } from "../providers/AuthProvider";
import { env } from "../../lib/config/env";
import { TabId } from "./Sidebar";
const LABELS: Record<TabId, [string, string]> = { dashboard: ["Workspace", "Dashboard"], chat: ["Workspace", "AI Assistant"], history: ["Workspace", "Workspace History"], rag: ["Knowledge", "Knowledge Base"], documents: ["Knowledge", "Documents"], models: ["AI Runtime", "Models"], sandbox: ["AI Runtime", "Sandbox"], audit: ["Security", "Audit Ledger"], access: ["Security", "User Management"], settings: ["System", "Settings"], about: ["System", "About AEGIS"] };
interface HeaderProps { activeTab: TabId; currentModelName?: string; documentCount?: number; onMenuToggle?: () => void; }
export default function Header({ activeTab, onMenuToggle }: HeaderProps) {
  const { user, logout } = useAuth(); const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  useEffect(() => { fetch(`${env.apiUrl}/health`).then((res) => res.json()).then((data) => setBackendHealthy(data.status === "ok")).catch(() => setBackendHealthy(false)); }, []);
  const [category, label] = LABELS[activeTab];
  return <header className="aegis-header"><Space size={12}><Button className="aegis-navigation-toggle" type="text" icon={<MenuOutlined />} aria-label="Open navigation menu" title="Open navigation menu" onClick={onMenuToggle} /><SafetyCertificateOutlined className="aegis-header-shield" /><Typography.Text strong className="aegis-header-brand">AEGIS</Typography.Text><Breadcrumb items={[{ title: category }, { title: label }]} /></Space><Space size={14}><Tag className="aegis-header-status"><Badge status={backendHealthy ? "success" : backendHealthy === false ? "error" : "processing"} /> {backendHealthy === false ? "NODE UNAVAILABLE" : "LOCAL NODE"}</Tag><Tag className="aegis-header-status aegis-header-local">AIR-GAPPED</Tag><Space size={8} className="aegis-header-user"><Avatar size={30} className="aegis-avatar">{(user?.username || "AG").slice(0, 2).toUpperCase()}</Avatar><Typography.Text strong>{user?.username}</Typography.Text><Button type="text" icon={<LogoutOutlined />} aria-label="Sign out" title="Sign out" onClick={logout} /></Space></Space></header>;
}
