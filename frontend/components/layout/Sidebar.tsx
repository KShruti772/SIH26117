"use client";

import React from "react";
import { Avatar, Badge, Button, Divider, Menu, Tag, Typography } from "antd";
import type { MenuProps } from "antd";
import { AppstoreOutlined, AuditOutlined, CloudServerOutlined, CodeOutlined, DatabaseOutlined, FileTextOutlined, HistoryOutlined, InfoCircleOutlined, LogoutOutlined, RobotOutlined, SafetyCertificateOutlined, SettingOutlined, TeamOutlined } from "@ant-design/icons";
import { useAuth } from "../providers/AuthProvider";

export type TabId = "dashboard" | "chat" | "rag" | "documents" | "models" | "sandbox" | "history" | "audit" | "access" | "settings" | "about";
interface SidebarProps { activeTab: TabId; setActiveTab: (tab: TabId) => void; isMobileDrawer?: boolean; }

export default function Sidebar({ activeTab, setActiveTab, isMobileDrawer = false }: SidebarProps) {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";
  const items: MenuProps["items"] = [
    { type: "group", label: "WORKSPACE", children: [{ key: "dashboard", icon: <AppstoreOutlined />, label: "Dashboard" }, { key: "chat", icon: <RobotOutlined />, label: "AI Assistant" }, { key: "history", icon: <HistoryOutlined />, label: "Workspace History" }] },
    { type: "group", label: "KNOWLEDGE", children: [{ key: "documents", icon: <FileTextOutlined />, label: "Documents" }, { key: "rag", icon: <DatabaseOutlined />, label: "Knowledge Base" }] },
    { type: "group", label: "AI RUNTIME", children: [{ key: "models", icon: <CloudServerOutlined />, label: "Models" }, { key: "sandbox", icon: <CodeOutlined />, label: "Sandbox" }] },
    ...(isAdmin ? [{ type: "group" as const, label: "SECURITY", children: [{ key: "access", icon: <TeamOutlined />, label: "User Management" }, { key: "audit", icon: <AuditOutlined />, label: "Audit Ledger" }] }] : []),
    { type: "group", label: "SYSTEM", children: [{ key: "settings", icon: <SettingOutlined />, label: "Settings" }, { key: "about", icon: <InfoCircleOutlined />, label: "About AEGIS" }] },
  ];
  return <div className={`aegis-sider-content ${isMobileDrawer ? "aegis-sider-mobile" : ""}`}>
    <div className="aegis-brand"><div className="aegis-brand-mark"><SafetyCertificateOutlined /></div><div><Typography.Text strong className="aegis-brand-title">AEGIS</Typography.Text><div className="aegis-brand-subtitle">Sovereign AI Workbench</div></div></div>
    <div className="aegis-node-status"><Badge status="success" /> LOCAL NODE OPERATIONAL</div>
    <Menu className="aegis-nav-menu" theme="dark" mode="inline" selectedKeys={[activeTab]} items={items} onClick={({ key }) => setActiveTab(key as TabId)} />
    <div className="aegis-sider-footer"><Divider /><div className="aegis-user-row"><Avatar size={34} className="aegis-avatar">{(user?.username || "AG").slice(0, 2).toUpperCase()}</Avatar><div className="aegis-user-meta"><Typography.Text strong ellipsis>{user?.username || "Operator"}</Typography.Text><Tag color={isAdmin ? "gold" : "blue"}>{isAdmin ? "ADMIN" : "OPERATOR"}</Tag></div><Button type="text" icon={<LogoutOutlined />} aria-label="Sign out" title="Sign out" onClick={logout} /></div></div>
  </div>;
}
