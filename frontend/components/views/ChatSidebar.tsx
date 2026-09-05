"use client";

import React from "react";
import { Button, Input, Popconfirm, Skeleton, Tooltip } from "antd";
import {
  ClockCircleOutlined,
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined
} from "@ant-design/icons";
import type { ConversationSession } from "../../lib/api/chat";

interface ChatSidebarProps {
  conversations: ConversationSession[];
  activeSessionId: string | null;
  loading: boolean;
  error: string | null;
  onSelectConversation: (sessionId: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (sessionId: string, e?: React.MouseEvent) => void;
  onRetry: () => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  title?: string | null;
}

function groupConversationsByDate(conversations: ConversationSession[]): {
  today: ConversationSession[];
  yesterday: ConversationSession[];
  older: ConversationSession[];
} {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 86400000;

  const today: ConversationSession[] = [];
  const yesterday: ConversationSession[] = [];
  const older: ConversationSession[] = [];

  conversations.forEach((conv) => {
    const timeStr = conv.last_message_at || conv.updated_at || conv.created_at;
    const convTime = new Date(timeStr).getTime();
    if (isNaN(convTime) || convTime >= todayStart) {
      today.push(conv);
    } else if (convTime >= yesterdayStart) {
      yesterday.push(conv);
    } else {
      older.push(conv);
    }
  });

  return { today, yesterday, older };
}

export default function ChatSidebar({
  conversations,
  activeSessionId,
  loading,
  error,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onRetry,
  searchQuery,
  setSearchQuery,
  title = "CONVERSATIONS"
}: ChatSidebarProps) {
  const filtered = conversations.filter(
    (c) =>
      !searchQuery.trim() ||
      (c.title && c.title.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const { today, yesterday, older } = groupConversationsByDate(filtered);

  const renderGroup = (groupTitle: string, items: ConversationSession[]) => {
    if (items.length === 0) return null;

    return (
      <div className="space-y-1.5 mb-5">
        <div className="flex items-center space-x-1.5 px-3 py-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
          <ClockCircleOutlined className="text-[10px]" />
          <span>{groupTitle}</span>
          <span className="text-slate-600 font-mono text-[10px]">({items.length})</span>
        </div>

        {items.map((conv) => {
          const isActive = activeSessionId === conv.id;
          const displayTime = new Date(
            conv.last_message_at || conv.updated_at || conv.created_at
          ).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
          });

          return (
            <div
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectConversation(conv.id);
                }
              }}
              role="button"
              tabIndex={0}
              className={`w-full p-3 rounded-lg border transition-colors cursor-pointer flex items-center justify-between group relative text-left ${
                isActive
                  ? "bg-blue-600/15 border-blue-500/40 text-slate-100 font-semibold"
                  : "bg-[#090e1a]/60 hover:bg-[#0f172a] border-slate-800/80 text-slate-300 hover:border-slate-700 font-medium"
              }`}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-7 w-1 rounded-r-full bg-blue-500" />
              )}

              <div className="flex-1 min-w-0 pr-2 space-y-1">
                <span className="text-xs font-semibold block truncate" title={conv.title}>
                  • {conv.title || "New Conversation"}
                </span>
                <div className="flex items-center space-x-2 text-[10px] text-slate-400">
                  <span className="font-mono text-slate-400">{displayTime}</span>
                </div>
              </div>

              <Popconfirm
                title="Delete this conversation?"
                description="This cannot be undone."
                okText="Delete"
                okButtonProps={{ danger: true }}
                onConfirm={() => onDeleteConversation(conv.id)}
              >
                <Tooltip title="Delete conversation">
                  <button
                    type="button"
                    onClick={(event) => event.stopPropagation()}
                    className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1.5 text-slate-400 hover:text-rose-400 transition-opacity cursor-pointer rounded-lg hover:bg-rose-500/10"
                    aria-label={`Delete ${conv.title || "conversation"}`}
                  >
                    <DeleteOutlined className="text-xs" />
                  </button>
                </Tooltip>
              </Popconfirm>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col bg-[#0d1322]/90 border border-slate-800/80 backdrop-blur-xl rounded-2xl overflow-hidden shadow-xl">
      {/* Panel Header */}
      <div className="p-4 border-b border-slate-800/80 space-y-3 bg-[#090e1a]/80 shrink-0">
        <div className="flex items-center justify-between">
          {title && <div className="flex items-center space-x-2"><MessageOutlined className="text-blue-400 text-sm" /><h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">{title}</h2></div>}
          <span className="text-[11px] text-slate-400 font-mono">
            {conversations.length} {conversations.length === 1 ? "session" : "sessions"}
          </span>
        </div>

        <Button
          onClick={onNewConversation}
          type="primary"
          icon={<PlusOutlined />}
          className="w-full h-9 flex items-center justify-center text-xs font-semibold shadow-md"
        >
          New conversation
        </Button>

        {/* Search filter */}
        <Input
          prefix={<SearchOutlined className="text-slate-500 text-xs" />}
          placeholder="Filter conversations…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          allowClear
          size="small"
          className="bg-[#050811] border-slate-800 text-xs"
        />
      </div>

      {/* Conversation List Stream */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        {loading && conversations.length === 0 ? (
          <div className="p-4 space-y-3">
            <Skeleton active paragraph={{ rows: 3 }} />
          </div>
        ) : error ? (
          <div className="p-4 text-center space-y-3">
            <p className="text-xs text-rose-400">{error}</p>
            <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
              Retry
            </Button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500 space-y-1">
            <p className="font-semibold text-slate-400">
              {searchQuery ? "No conversations match your filter." : "No conversations yet"}
            </p>
            {!searchQuery && (
              <p className="text-[11px] text-slate-500">Start a new conversation to begin.</p>
            )}
          </div>
        ) : (
          <div>
            {renderGroup("Today", today)}
            {renderGroup("Yesterday", yesterday)}
            {renderGroup("Older", older)}
          </div>
        )}
      </div>
    </div>
  );
}
