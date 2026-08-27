"use client";

import React from "react";
import Sidebar, { TabId } from "./Sidebar";
import Header from "./Header";
import PageContainer from "./PageContainer";

interface AppShellProps {
  children: React.ReactNode;
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
}

export default function AppShell({ children, activeTab, setActiveTab }: AppShellProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0a0f1d] text-slate-100">
      {/* Navigation Dock */}
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Pane */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />
        <PageContainer>
          {children}
        </PageContainer>
      </div>
    </div>
  );
}
