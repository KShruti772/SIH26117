"use client";
import React, { useState } from "react";
import { Drawer, Layout } from "antd";
import Sidebar, { TabId } from "./Sidebar";
import Header from "./Header";
import PageContainer from "./PageContainer";
const { Sider, Content } = Layout;
interface AppShellProps { children: React.ReactNode; activeTab: TabId; setActiveTab: (tab: TabId) => void; currentModelName?: string; documentCount?: number; }
export default function AppShell(props: AppShellProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  return <Layout className="aegis-app-shell"><Sider width={272} className="aegis-desktop-sider" theme="dark" trigger={null}><Sidebar activeTab={props.activeTab} setActiveTab={props.setActiveTab} /></Sider><Drawer placement="left" open={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} closable={false} className="aegis-mobile-drawer" size={288} styles={{ body: { padding: 0 } }}><Sidebar activeTab={props.activeTab} setActiveTab={(tab) => { props.setActiveTab(tab); setMobileMenuOpen(false); }} isMobileDrawer /></Drawer><Layout className="aegis-main-layout"><Header activeTab={props.activeTab} currentModelName={props.currentModelName} documentCount={props.documentCount} onMenuToggle={() => setMobileMenuOpen(true)} /><Content><PageContainer>{props.children}</PageContainer></Content></Layout></Layout>;
}
