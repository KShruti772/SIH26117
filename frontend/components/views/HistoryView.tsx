"use client";

import React, { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Empty,
  Input,
  Radio,
  Space,
  Tag,
  Typography
} from "antd";
import {
  ClockCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined
} from "@ant-design/icons";
import type { ConversationSession } from "../../lib/api/chat";
import type { SandboxHistoryItem } from "./SandboxView";
import type { RagQueryResponse, GroundedAnswerResponse } from "../../lib/api/rag";

export interface KnowledgeHistoryItem {
  id: string;
  query: string;
  timestamp: string;
  response: GroundedAnswerResponse | RagQueryResponse | null;
}

export type HistoryFilterCategory = "ALL" | "AI" | "KNOWLEDGE" | "CODE";

interface HistoryViewProps {
  conversations: ConversationSession[];
  conversationsLoading: boolean;
  conversationsError: string | null;
  onRefreshConversations: () => void;
  onSelectConversation: (sessionId: string) => void;
  onDeleteConversation: (sessionId: string, e: React.MouseEvent) => void;
  
  sandboxHistory: SandboxHistoryItem[];
  onSelectSandbox: (item: SandboxHistoryItem) => void;
  onClearSandboxHistory: () => void;

  knowledgeHistory: KnowledgeHistoryItem[];
  onSelectKnowledge: (item: KnowledgeHistoryItem) => void;
  onClearKnowledgeHistory: () => void;

  onNavigateTab: (tab: "chat" | "rag" | "sandbox") => void;
}

interface UnifiedHistoryItem {
  id: string;
  category: "AI" | "KNOWLEDGE" | "CODE";
  title: string;
  subtitle?: string;
  timestamp: string;
  badgeText?: string;
  badgeColor?: string;
  rawItem: any;
}

function groupItemsByDate(items: UnifiedHistoryItem[]): {
  today: UnifiedHistoryItem[];
  yesterday: UnifiedHistoryItem[];
  older: UnifiedHistoryItem[];
} {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;

  const today: UnifiedHistoryItem[] = [];
  const yesterday: UnifiedHistoryItem[] = [];
  const older: UnifiedHistoryItem[] = [];

  items.forEach((item) => {
    const itemTime = new Date(item.timestamp).getTime();
    if (isNaN(itemTime) || itemTime >= todayStart) {
      today.push(item);
    } else if (itemTime >= yesterdayStart) {
      yesterday.push(item);
    } else {
      older.push(item);
    }
  });

  return { today, yesterday, older };
}

export default function HistoryView(props: HistoryViewProps) {
  const [filter, setFilter] = useState<HistoryFilterCategory>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Build unified items list
  const unifiedItems: UnifiedHistoryItem[] = [];

  // 1. AI Conversations
  props.conversations.forEach((c) => {
    unifiedItems.push({
      id: `conv_${c.id}`,
      category: "AI",
      title: c.title || "Conversation Session",
      subtitle: c.last_message_at ? `Last active: ${new Date(c.last_message_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : undefined,
      timestamp: c.updated_at || c.created_at || new Date().toISOString(),
      badgeText: "AI ASSISTANT",
      badgeColor: "blue",
      rawItem: c
    });
  });

  // 2. Knowledge Searches
  props.knowledgeHistory.forEach((k) => {
    unifiedItems.push({
      id: `rag_${k.id}`,
      category: "KNOWLEDGE",
      title: k.query,
      subtitle: k.response ? ("count" in k.response ? `Retrieved ${k.response.count} evidence chunks` : "Document Q&A Analysis") : "Query search",
      timestamp: k.timestamp,
      badgeText: "KNOWLEDGE",
      badgeColor: "cyan",
      rawItem: k
    });
  });

  // 3. Code Executions
  props.sandboxHistory.forEach((s) => {
    unifiedItems.push({
      id: `code_${s.id}`,
      category: "CODE",
      title: s.code.split("\n")[0].substring(0, 60) || "Python Execution",
      subtitle: s.response ? `Exit: ${s.response.exit_code} · Time: ${s.response.duration_ms}ms` : "Sandbox run",
      timestamp: s.timestamp,
      badgeText: "SANDBOX",
      badgeColor: "purple",
      rawItem: s
    });
  });

  // Sort descending by timestamp
  unifiedItems.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  // Filter by category and search
  const filteredItems = unifiedItems.filter((item) => {
    const matchesCategory = filter === "ALL" || item.category === filter;
    const matchesSearch = !searchQuery.trim() || item.title.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const { today, yesterday, older } = groupItemsByDate(filteredItems);

  const handleClickItem = (item: UnifiedHistoryItem) => {
    if (item.category === "AI") {
      props.onSelectConversation(item.rawItem.id);
      props.onNavigateTab("chat");
    } else if (item.category === "KNOWLEDGE") {
      props.onSelectKnowledge(item.rawItem);
      props.onNavigateTab("rag");
    } else if (item.category === "CODE") {
      props.onSelectSandbox(item.rawItem);
      props.onNavigateTab("sandbox");
    }
  };

  const renderSection = (title: string, list: UnifiedHistoryItem[]) => {
    if (list.length === 0) return null;

    return (
      <div className="space-y-3 mb-6">
        <div className="flex items-center space-x-2 px-1">
          <ClockCircleOutlined className="text-slate-400 text-xs" />
          <Typography.Text strong className="text-xs text-slate-300 uppercase tracking-wider">
            {title} ({list.length})
          </Typography.Text>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {list.map((item) => (
            <div
              key={item.id}
              onClick={() => handleClickItem(item)}
              className="p-4 bg-[#0d1322] hover:bg-[#131b2e] border border-slate-800 hover:border-blue-500/50 rounded-xl cursor-pointer transition-all space-y-2 group shadow-sm"
            >
              <div className="flex items-center justify-between">
                <Tag color={item.badgeColor} className="!mr-0 font-bold text-[10px]">
                  {item.badgeText}
                </Tag>
                <Typography.Text type="secondary" className="text-[11px] font-mono">
                  {new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </Typography.Text>
              </div>
              <Typography.Paragraph
                ellipsis={{ rows: 2 }}
                className="!mb-1 font-semibold text-slate-100 group-hover:text-blue-400 transition-colors text-sm"
              >
                {item.title}
              </Typography.Paragraph>
              {item.subtitle && (
                <div className="text-xs text-slate-400 font-mono truncate">
                  {item.subtitle}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="aegis-view-stack">
      {/* Heading */}
      <section className="aegis-view-heading">
        <div>
          <Typography.Title level={2} className="!mb-1">
            Workspace History
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Unified chronological access to your AI conversations, knowledge queries, and sandbox executions.
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={props.onRefreshConversations} loading={props.conversationsLoading}>
            Refresh
          </Button>
        </Space>
      </section>

      {/* Filter and Search Controls */}
      <Card className="aegis-panel-card mb-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <Radio.Group
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            buttonStyle="solid"
            size="middle"
          >
            <Radio.Button value="ALL">
              <Space size="small">
                <span>ALL</span>
                <Badge count={unifiedItems.length} style={{ backgroundColor: "#334155" }} />
              </Space>
            </Radio.Button>
            <Radio.Button value="AI">
              <Space size="small">
                <RobotOutlined />
                <span>AI ASSISTANT</span>
                <Badge count={props.conversations.length} style={{ backgroundColor: "#1e3a8a" }} />
              </Space>
            </Radio.Button>
            <Radio.Button value="KNOWLEDGE">
              <Space size="small">
                <DatabaseOutlined />
                <span>KNOWLEDGE BASE</span>
                <Badge count={props.knowledgeHistory.length} style={{ backgroundColor: "#0e7490" }} />
              </Space>
            </Radio.Button>
            <Radio.Button value="CODE">
              <Space size="small">
                <CodeOutlined />
                <span>SANDBOX</span>
                <Badge count={props.sandboxHistory.length} style={{ backgroundColor: "#581c87" }} />
              </Space>
            </Radio.Button>
          </Radio.Group>

          <Input
            placeholder="Search history items..."
            prefix={<SearchOutlined />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ maxWidth: 300 }}
            allowClear
          />
        </div>
      </Card>

      {/* History Listing */}
      {filteredItems.length === 0 ? (
        <Card className="aegis-panel-card p-8 text-center">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              searchQuery
                ? `No history items matching "${searchQuery}".`
                : "No workspace history recorded yet."
            }
          />
        </Card>
      ) : (
        <div>
          {renderSection("Today", today)}
          {renderSection("Yesterday", yesterday)}
          {renderSection("Older", older)}
        </div>
      )}
    </div>
  );
}
