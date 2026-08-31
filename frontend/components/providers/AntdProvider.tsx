"use client";

import { ConfigProvider, theme } from "antd";

/** Shared Ant Design theme for the AEGIS sovereign workbench. */
export function AntdProvider({ children }: { children: React.ReactNode }) {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: "#3b9cff",
          colorInfo: "#3b9cff",
          colorSuccess: "#43c59e",
          colorWarning: "#e7a94e",
          colorError: "#e06868",
          colorBgBase: "#0b1018",
          colorBgContainer: "#111925",
          colorBgElevated: "#161f2c",
          colorBorder: "#263244",
          colorBorderSecondary: "#1d2938",
          colorText: "#edf3fa",
          colorTextSecondary: "#9baabd",
          borderRadius: 10,
          controlHeight: 38,
          fontSize: 14,
          fontFamily: "var(--font-geist-sans), -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        },
        components: {
          Button: { primaryShadow: "none", defaultShadow: "none" },
          Card: { paddingLG: 20 },
          Menu: { darkItemBg: "#0b1018", darkSubMenuItemBg: "#0b1018" },
          Table: { headerBg: "#0e1621", rowHoverBg: "#152131" },
        },
      }}
    >
      {children}
    </ConfigProvider>
  );
}
