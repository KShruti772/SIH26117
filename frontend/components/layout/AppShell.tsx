"use client";

import React, { useState } from "react";
import Sidebar, { TabId } from "./Sidebar";
import Header from "./Header";
import PageContainer from "./PageContainer";

interface AppShellProps {
  children: React.ReactNode;
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  currentModelName?: string;
  documentCount?: number;
}

export default function AppShell({ 
  children, 
  activeTab, 
  setActiveTab,
  currentModelName,
  documentCount
}: AppShellProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#070c14] text-slate-100 font-sans">
      
      {/* 1. Mobile Menu Sidebar Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex md:hidden font-sans">
          {/* Backdrop overlay */}
          <div 
            onClick={() => setMobileMenuOpen(false)}
            className="fixed inset-0 bg-black/70 backdrop-blur-xs transition-opacity" 
          />
          {/* Drawer Wrapper */}
          <div className="relative flex-1 flex flex-col max-w-[260px] w-full bg-[#070c14] transition-transform duration-300">
            <Sidebar 
              activeTab={activeTab} 
              setActiveTab={(tab) => {
                setActiveTab(tab);
                setMobileMenuOpen(false);
              }} 
              isMobileDrawer={true} 
            />
          </div>
        </div>
      )}

      {/* 2. Static Sidebar Nav for Tablet & Desktop views */}
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* 3. Main Content Workspace Layout */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header 
          activeTab={activeTab} 
          currentModelName={currentModelName} 
          documentCount={documentCount} 
          onMenuToggle={() => setMobileMenuOpen(true)}
        />
        <PageContainer>
          {children}
        </PageContainer>
      </div>
    </div>
  );
}
