"use client";

import React from "react";
import { Button, Card, Col, Empty, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import { DatabaseOutlined, FileTextOutlined, MessageOutlined, RobotOutlined, SafetyCertificateOutlined, ThunderboltOutlined } from "@ant-design/icons";
import type { AuditLog } from "../../lib/api/audit";

interface DashboardViewProps {
  username?: string;
  role?: string;
  activeModelName: string;
  documentCount: number;
  documentsLoading: boolean;
  conversationCount: number;
  conversationsLoading: boolean;
  recentLogs: AuditLog[];
  onNavigate: (tab: "chat" | "documents" | "rag" | "models" | "sandbox" | "audit") => void;
  onNewConversation: () => void;
  latestMessage?: { content: string; sourceCount?: number };
}

export default function DashboardView(props: DashboardViewProps) {
  const columns = [
    { title: "Time", dataIndex: "timestamp", width: 105, render: (value: string) => <Typography.Text type="secondary" className="font-mono text-[11px]">{new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</Typography.Text> },
    { title: "Operator", dataIndex: "username", render: (value: string | null) => value || "System" },
    { title: "Action", dataIndex: "action", render: (value: string) => <Typography.Text className="text-[#83c5f7] font-mono text-xs">{value}</Typography.Text> },
    { title: "Component", dataIndex: "component", responsive: ["md"] as ("md")[] },
    { title: "Status", dataIndex: "status", align: "right" as const, render: (value: string) => <Tag color={value === "success" ? "success" : "error"}>{value.toUpperCase()}</Tag> },
  ];
  return <div className="aegis-view-stack">
    <section className="aegis-view-heading">
      <div><Typography.Title level={2}>Good to see you, {props.username || "Operator"}</Typography.Title><Typography.Paragraph>Monitor your local AI workspace, knowledge assets, and security posture from one place.</Typography.Paragraph></div>
      <Space wrap><Tag color="blue">LOCAL INFERENCE</Tag><Tag color="cyan">AIR-GAPPED</Tag><Tag color="success">RBAC ENABLED</Tag></Space>
    </section>
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} xl={6}><Card className="aegis-stat-card"><Space><RobotOutlined /><Typography.Text type="secondary">ACTIVE MODEL</Typography.Text></Space><Typography.Title level={4} ellipsis={{ tooltip: props.activeModelName }}>{props.activeModelName}</Typography.Title><Tag color="blue">LOCAL</Tag></Card></Col>
      <Col xs={24} sm={12} xl={6}><Card className="aegis-stat-card"><Space><DatabaseOutlined /><Typography.Text type="secondary">KNOWLEDGE BASE</Typography.Text></Space><Statistic value={props.documentCount} loading={props.documentsLoading} suffix="documents" /><Tag color="success">INDEXED</Tag></Card></Col>
      <Col xs={24} sm={12} xl={6}><Card className="aegis-stat-card"><Space><MessageOutlined /><Typography.Text type="secondary">CONVERSATIONS</Typography.Text></Space><Statistic value={props.conversationCount} loading={props.conversationsLoading} suffix="sessions" /><Tag color="blue">ACTIVE</Tag></Card></Col>
      <Col xs={24} sm={12} xl={6}><Card className="aegis-stat-card"><Space><SafetyCertificateOutlined /><Typography.Text type="secondary">SECURITY</Typography.Text></Space><Typography.Title level={3} className="!text-[#66cba9]">SECURE</Typography.Title><Tag color="success">AUDIT ENABLED</Tag></Card></Col>
    </Row>
    <Row gutter={[16, 16]}>
      <Col xs={24} xl={15}><Card title={<Space><RobotOutlined />AI Assistant</Space>} extra={<Button type="primary" onClick={() => props.onNavigate("chat")}>Open assistant</Button>} className="aegis-panel-card">
        {props.latestMessage ? <div className="aegis-dashboard-preview"><Typography.Text type="secondary">LATEST CONVERSATION</Typography.Text><Typography.Paragraph ellipsis={{ rows: 3, expandable: true }}>{props.latestMessage.content}</Typography.Paragraph>{props.latestMessage.sourceCount ? <Tag color="success">Grounded on {props.latestMessage.sourceCount} sources</Tag> : <Tag>General reasoning</Tag>}</div> : <Empty description="Start a secure local conversation to begin." image={Empty.PRESENTED_IMAGE_SIMPLE}><Button onClick={props.onNewConversation}>Create conversation</Button></Empty>}
      </Card></Col>
      <Col xs={24} xl={9}><Card title={<Space><ThunderboltOutlined />Quick actions</Space>} className="aegis-panel-card"><div className="aegis-action-grid"><Button icon={<FileTextOutlined />} onClick={() => props.onNavigate("documents")}>Upload document</Button><Button icon={<MessageOutlined />} onClick={props.onNewConversation}>New conversation</Button><Button icon={<DatabaseOutlined />} onClick={() => props.onNavigate("rag")}>Query knowledge base</Button><Button icon={<RobotOutlined />} onClick={() => props.onNavigate("models")}>Manage models</Button></div></Card></Col>
      <Col span={24}><Card title="Recent system activity" extra={props.role === "admin" ? <Button type="link" onClick={() => props.onNavigate("audit")}>View audit ledger</Button> : null} className="aegis-panel-card"><Table rowKey="id" size="middle" pagination={false} scroll={{ x: 650 }} columns={columns} dataSource={props.recentLogs} locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No recorded activity yet." /> }} /></Card></Col>
    </Row>
  </div>;
}
