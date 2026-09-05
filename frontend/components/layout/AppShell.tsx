"use client";
import React, { useState } from "react";
import { Drawer, Layout } from "antd";
import Sidebar, { TabId } from "./Sidebar";
import Header from "./Header";
import PageContainer from "./PageContainer";
const { Content } = Layout;
interface AppShellProps { children: React.ReactNode; activeTab: TabId; setActiveTab: (tab: TabId) => void; currentModelName?: string; documentCount?: number; }
export default function AppShell(props: AppShellProps) {
  const [navigationOpen, setNavigationOpen] = useState(false);

  return (
    <Layout className="aegis-app-shell">
      <Drawer
        placement="left"
        open={navigationOpen}
        onClose={() => setNavigationOpen(false)}
        closable
        title={null}
        className="aegis-navigation-drawer"
        size={288}
        styles={{ body: { padding: 0 } }}
      >
        <Sidebar
          activeTab={props.activeTab}
          setActiveTab={(tab) => {
            props.setActiveTab(tab);
            setNavigationOpen(false);
          }}
          isMobileDrawer
        />
      </Drawer>
      <Layout className="aegis-main-layout">
        <Header
          activeTab={props.activeTab}
          currentModelName={props.currentModelName}
          documentCount={props.documentCount}
          onMenuToggle={() => setNavigationOpen(true)}
        />
        <Content><PageContainer>{props.children}</PageContainer></Content>
      </Layout>
    </Layout>
  );
}
