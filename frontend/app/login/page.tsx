"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, Button, Card, Form, Input, Space, Tag, Typography } from "antd";
import { EyeInvisibleOutlined, EyeTwoTone, LockOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useAuth } from "../../components/providers/AuthProvider";

export default function LoginPage() {
  const { user, login } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expiredNotice, setExpiredNotice] = useState(false);

  useEffect(() => { if (user) router.replace("/"); }, [user, router]);
  useEffect(() => { setExpiredNotice(new URLSearchParams(window.location.search).get("expired") === "true"); }, []);

  const handleSubmit = async ({ username, password }: { username: string; password: string }) => {
    setError(null); setExpiredNotice(false); setLoading(true);
    try { await login({ username: username.trim(), password }); router.push("/"); }
    catch (err: unknown) {
      const apiError = err as { message?: string; status?: number };
      const msg = apiError.message || "";
      setError(msg.includes("Failed to fetch") || msg.includes("Network error") || apiError.status === 0 ? "Unable to connect to the AEGIS backend. Please ensure the local backend service is running." : msg.includes("401") || msg.includes("credentials") || msg.includes("Unauthorized") || msg.includes("password") || msg.includes("Invalid") ? "Invalid username or password." : "Something went wrong while signing you in. Please try again.");
    } finally { setLoading(false); }
  };

  return <main className="aegis-login-page"><header className="aegis-login-header"><Space size={10}><span className="aegis-login-mark"><SafetyCertificateOutlined /></span><span><Typography.Text strong>AEGIS</Typography.Text><Typography.Text type="secondary">Sovereign AI Workbench</Typography.Text></span></Space><Tag color="success">ON-PREMISE • AIR-GAPPED</Tag></header><section className="aegis-login-content"><Card className="aegis-login-card"><div className="aegis-login-intro"><span className="aegis-login-lock"><LockOutlined /></span><Typography.Title level={2}>Secure sign in</Typography.Title><Typography.Paragraph>Access your organization&apos;s private AI workspace.</Typography.Paragraph></div>{expiredNotice && <Alert className="mb-5" type="warning" showIcon title="Your session has expired. Please sign in again to continue." />}{error && <Alert className="mb-5" type="error" showIcon title={error} />}<Form layout="vertical" requiredMark={false} onFinish={handleSubmit} autoComplete="on"><Form.Item name="username" label="Username" rules={[{ required: true, whitespace: true, message: "Please enter your username." }]}><Input autoComplete="username" placeholder="Enter your username" size="large" /></Form.Item><Form.Item name="password" label="Password" rules={[{ required: true, message: "Please enter your password." }]}><Input.Password autoComplete="current-password" placeholder="Enter your password" iconRender={(visible) => visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />} size="large" /></Form.Item><Button htmlType="submit" type="primary" size="large" block loading={loading}>Sign in securely</Button></Form><div className="aegis-login-footnote"><span>Local deployment</span><span>Privacy-first</span><span>Enterprise security</span></div></Card></section><footer className="aegis-login-footer">AEGIS Sovereign AI Infrastructure</footer></main>;
}
