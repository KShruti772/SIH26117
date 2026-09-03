"use client";

import React from "react";
import {
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography
} from "antd";
import {
  DatabaseOutlined,
  FileTextOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined
} from "@ant-design/icons";
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
    {
      title: "Time",
      dataIndex: "timestamp",
      width: 105,
      render: (value: string) => (
        <Typography.Text type="secondary" className="font-mono text-[11px]">
          {new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </Typography.Text>
      )
    },
    {
      title: "Operator",
      dataIndex: "username",
      render: (value: string | null) => value || "System"
    },
    {
      title: "Action",
      dataIndex: "action",
      render: (value: string) => (
        <Typography.Text className="text-[#83c5f7] font-mono text-xs">
          {value}
        </Typography.Text>
      )
    },
    {
      title: "Component",
      dataIndex: "component",
      responsive: ["md"] as ("md")[]
    },
    {
      title: "Status",
      dataIndex: "status",
      align: "right" as const,
      render: (value: string) => (
        <Tag color={value === "success" ? "success" : "error"} className="font-mono text-[10px] font-bold">
          {value.toUpperCase()}
        </Tag>
      )
    }
  ];

  const docSuffix = props.documentCount === 1 ? "document" : "documents";
  const convSuffix = props.conversationCount === 1 ? "conversation" : "conversations";

  return (
    <div className="aegis-view-stack space-y-6">
      {/* View Header */}
      <section className="aegis-view-heading">
        <div>
          <Typography.Title level={2} className="!mb-1">
            Good to see you, {props.username || "Operator"}
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Monitor your local AI workspace, knowledge assets, and security posture from one place.
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Tag color="blue">LOCAL INFERENCE</Tag>
          <Tag color="cyan">AIR-GAPPED</Tag>
          <Tag color="success">RBAC ENABLED</Tag>
        </Space>
      </section>

      {/* 4 Real Metric Cards */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <Card className="aegis-stat-card">
            <Space className="mb-1">
              <RobotOutlined className="text-blue-400" />
              <Typography.Text type="secondary" className="text-xs uppercase font-bold tracking-wider">
                ACTIVE MODEL
              </Typography.Text>
            </Space>
            <Typography.Title level={4} className="!mb-2 !text-slate-100 font-mono truncate" title={props.activeModelName}>
              {props.activeModelName || "No active model"}
            </Typography.Title>
            <Tag color="blue" className="font-mono text-[10px]">LOCAL OLLAMA</Tag>
          </Card>
        </Col>

        <Col xs={24} sm={12} xl={6}>
          <Card className="aegis-stat-card">
            <Space className="mb-1">
              <DatabaseOutlined className="text-indigo-400" />
              <Typography.Text type="secondary" className="text-xs uppercase font-bold tracking-wider">
                KNOWLEDGE BASE
              </Typography.Text>
            </Space>
            <Statistic
              value={props.documentCount}
              loading={props.documentsLoading}
              suffix={<span className="text-xs text-slate-400 font-normal font-sans ml-1">{docSuffix}</span>}
            />
            <Tag color="success" className="font-mono text-[10px]">INDEXED</Tag>
          </Card>
        </Col>

        <Col xs={24} sm={12} xl={6}>
          <Card className="aegis-stat-card">
            <Space className="mb-1">
              <MessageOutlined className="text-emerald-400" />
              <Typography.Text type="secondary" className="text-xs uppercase font-bold tracking-wider">
                CONVERSATIONS
              </Typography.Text>
            </Space>
            <Statistic
              value={props.conversationCount}
              loading={props.conversationsLoading}
              suffix={<span className="text-xs text-slate-400 font-normal font-sans ml-1">{convSuffix}</span>}
            />
            <Tag color="blue" className="font-mono text-[10px]">PERSISTED</Tag>
          </Card>
        </Col>

        <Col xs={24} sm={12} xl={6}>
          <Card className="aegis-stat-card">
            <Space className="mb-1">
              <SafetyCertificateOutlined className="text-emerald-400" />
              <Typography.Text type="secondary" className="text-xs uppercase font-bold tracking-wider">
                SECURITY
              </Typography.Text>
            </Space>
            <Typography.Title level={3} className="!mb-2 !text-[#66cba9] font-bold">
              SECURE
            </Typography.Title>
            <Tag color="success" className="font-mono text-[10px]">AUDIT ENABLED</Tag>
          </Card>
        </Col>
      </Row>

      {/* Main Panels */}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card
            title={
              <Space>
                <RobotOutlined />
                <span>AI Assistant</span>
              </Space>
            }
            extra={
              <Button type="primary" onClick={() => props.onNavigate("chat")}>
                Open assistant
              </Button>
            }
            className="aegis-panel-card"
          >
            {props.latestMessage ? (
              <div className="aegis-dashboard-preview p-4 bg-[#080d1a] border border-slate-800 rounded-xl space-y-2">
                <Typography.Text type="secondary" className="text-[11px] font-bold uppercase tracking-wider block text-slate-400">
                  LATEST CONVERSATION
                </Typography.Text>
                <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }} className="!mb-2 text-slate-200 text-sm">
                  {props.latestMessage.content}
                </Typography.Paragraph>
                {props.latestMessage.sourceCount ? (
                  <Tag color="success">Grounded on {props.latestMessage.sourceCount} sources</Tag>
                ) : (
                  <Tag>General reasoning</Tag>
                )}
              </div>
            ) : (
              <Empty
                description="Start a secure local conversation to begin."
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button onClick={props.onNewConversation}>Create conversation</Button>
              </Empty>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={9}>
          <Card
            title={
              <Space>
                <ThunderboltOutlined />
                <span>Quick actions</span>
              </Space>
            }
            className="aegis-panel-card"
          >
            <div className="aegis-action-grid grid grid-cols-2 gap-3">
              <Button
                icon={<FileTextOutlined />}
                onClick={() => props.onNavigate("documents")}
                className="h-12 flex items-center justify-start text-xs"
              >
                Upload document
              </Button>
              <Button
                icon={<MessageOutlined />}
                onClick={props.onNewConversation}
                className="h-12 flex items-center justify-start text-xs"
              >
                New conversation
              </Button>
              <Button
                icon={<DatabaseOutlined />}
                onClick={() => props.onNavigate("rag")}
                className="h-12 flex items-center justify-start text-xs"
              >
                Query knowledge
              </Button>
              <Button
                icon={<RobotOutlined />}
                onClick={() => props.onNavigate("models")}
                className="h-12 flex items-center justify-start text-xs"
              >
                Manage models
              </Button>
            </div>
          </Card>
        </Col>

        <Col span={24}>
          <Card
            title="Recent system activity"
            extra={
              props.role === "admin" ? (
                <Button type="link" onClick={() => props.onNavigate("audit")}>
                  View audit ledger
                </Button>
              ) : null
            }
            className="aegis-panel-card"
          >
            <Table
              rowKey="id"
              size="middle"
              pagination={false}
              scroll={{ x: 650 }}
              columns={columns}
              dataSource={props.recentLogs}
              locale={{
                emptyText: (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="No recorded activity yet."
                  />
                )
              }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
