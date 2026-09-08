"use client";

import React, { useState, useEffect } from "react";
import { Drawer, Layout } from "antd";
import Sidebar, { TabId } from "./Sidebar";
import Header from "./Header";
import PageContainer from "./PageContainer";

const { Content, Sider } = Layout;

interface AppShellProps {
  children: React.ReactNode;
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  currentModelName?: string;
  documentCount?: number;
}

export default function AppShell(props: AppShellProps) {
  // Navigation menu state: persists across client-side workspace changes on desktop
  const [desktopNavOpen, setDesktopNavOpen] = useState<boolean>(false);
  const [mobileNavOpen, setMobileNavOpen] = useState<boolean>(false);
  const [isMobile, setIsMobile] = useState<boolean>(false);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) {
        // When screen is mobile, desktop Sider collapses
        setDesktopNavOpen(false);
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleMenuToggle = () => {
    if (isMobile) {
      setMobileNavOpen((prev) => !prev);
    } else {
      setDesktopNavOpen((prev) => !prev);
    }
  };

  const isMenuOpen = isMobile ? mobileNavOpen : desktopNavOpen;

  return (
    <Layout className="aegis-app-shell">
      {/* Desktop Persistent Collapsible Sidebar */}
      {!isMobile && (
        <Sider
          width={280}
          collapsedWidth={0}
          collapsed={!desktopNavOpen}
          trigger={null}
          className="aegis-desktop-sider"
          style={{
            background: "#0b1018",
            borderRight: desktopNavOpen ? "1px solid #202c3b" : "none",
            transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)"
          }}
        >
          <Sidebar
            activeTab={props.activeTab}
            setActiveTab={props.setActiveTab}
            isMobileDrawer={false}
          />
        </Sider>
      )}

      {/* Mobile Responsive Navigation Drawer */}
      <Drawer
        placement="left"
        open={isMobile && mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
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
            setMobileNavOpen(false);
          }}
          isMobileDrawer
        />
      </Drawer>

      <Layout className="aegis-main-layout">
        <Header
          activeTab={props.activeTab}
          currentModelName={props.currentModelName}
          documentCount={props.documentCount}
          menuOpen={isMenuOpen}
          onMenuToggle={handleMenuToggle}
        />
        <Content>
          <PageContainer>{props.children}</PageContainer>
        </Content>
      </Layout>
    </Layout>
  );
}
