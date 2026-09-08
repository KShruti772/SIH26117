"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Alert,
  Badge,
  Button as AntButton,
  Card as AntCard,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  App,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  EditOutlined,
  EyeOutlined,
  FileDoneOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileWordOutlined,
  HistoryOutlined,
  LoadingOutlined,
  LockOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  StopOutlined,
  UserOutlined,
  WarningOutlined
} from "@ant-design/icons";
import {
  approvalsApi,
  ApprovalItem,
  ApprovalDetail,
  ApprovalStatusType,
  ApprovalResolutionResult
} from "../../lib/api/approvals";
import { ragApi } from "../../lib/api/rag";
import { useAuth } from "../providers/AuthProvider";
import { getToken } from "../../lib/security/token";
import { env } from "../../lib/config/env";
import SafeMarkdown from "../ui/SafeMarkdown";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const REVIEWER_ROLES = new Set(["admin", "reviewer", "supervisor", "lead"]);

interface ApprovalsViewProps {
  initialApprovalId?: string | null;
  onClearInitialId?: () => void;
  onNavigateToTab?: (tab: string) => void;
  onApprovalResolved?: (approvalId: string, result: ApprovalResolutionResult) => void;
}

export default function ApprovalsView({
  initialApprovalId,
  onClearInitialId,
  onNavigateToTab,
  onApprovalResolved
}: ApprovalsViewProps) {
  const { user } = useAuth();
  const { message } = App.useApp();
  const userRole = (user?.role || "user").toLowerCase();
  const isAuthorizedReviewer = REVIEWER_ROLES.has(userRole);

  // State: Queue listing
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("WAITING_FOR_HUMAN");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // State: Selected Approval Detail Drawer
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(initialApprovalId || null);
  const [approvalDetail, setApprovalDetail] = useState<ApprovalDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // State: Decision Modals & Actions
  const [approveModalOpen, setApproveModalOpen] = useState<boolean>(false);
  const [approveComment, setApproveComment] = useState<string>("");
  
  const [modifyModalOpen, setModifyModalOpen] = useState<boolean>(false);
  const [modifyRevisedText, setModifyRevisedText] = useState<string>("");
  const [modifyComment, setModifyComment] = useState<string>("");

  const [rejectModalOpen, setRejectModalOpen] = useState<boolean>(false);
  const [rejectReason, setRejectReason] = useState<string>("");

  // State: Async Action Execution Progress
  const [actionInProgress, setActionInProgress] = useState<boolean>(false);
  const [actionProgressMessage, setActionProgressMessage] = useState<string>("");
  const [resolutionResult, setResolutionResult] = useState<ApprovalResolutionResult | null>(null);
  const [downloadingDocId, setDownloadingDocId] = useState<string | null>(null);

  // Load approvals queue from backend API (Reviewer-only operation)
  const loadApprovals = useCallback(async () => {
    if (!isAuthorizedReviewer) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      let res;
      if (statusFilter === "WAITING_FOR_HUMAN") {
        res = await approvalsApi.listPending();
      } else if (statusFilter === "ALL") {
        res = await approvalsApi.listAll();
      } else {
        res = await approvalsApi.listAll({ status: statusFilter });
      }
      setApprovals(res.approvals || []);
    } catch (err: any) {
      const msg = err.detail || err.message || "Failed to load approval requests queue.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, isAuthorizedReviewer]);

  // Initial load and filter change trigger
  useEffect(() => {
    void loadApprovals();
  }, [loadApprovals]);

  // Open specific approval detail if initialApprovalId is passed
  useEffect(() => {
    if (initialApprovalId) {
      setSelectedApprovalId(initialApprovalId);
      if (onClearInitialId) {
        onClearInitialId();
      }
    }
  }, [initialApprovalId, onClearInitialId]);

  // Load single approval detail when an item is selected
  const loadApprovalDetail = useCallback(async (approvalId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    setResolutionResult(null);
    try {
      const res = await approvalsApi.getById(approvalId);
      setApprovalDetail(res.approval);
      // Pre-fill modify form with existing draft text if available
      if (res.approval.proposed_payload?.draft_document_text) {
        setModifyRevisedText(res.approval.proposed_payload.draft_document_text);
      } else {
        setModifyRevisedText("");
      }
    } catch (err: any) {
      const msg = err.detail || err.message || "Failed to retrieve approval request details.";
      setDetailError(msg);
      if (err.status === 404) {
        message.error("This approval request was not found.");
      } else if (err.status === 403) {
        message.error("You are not authorized to view this approval request.");
      }
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedApprovalId) {
      void loadApprovalDetail(selectedApprovalId);
    } else {
      setApprovalDetail(null);
      setDetailError(null);
      setResolutionResult(null);
    }
  }, [selectedApprovalId, loadApprovalDetail]);

  // Download generated deliverable document
  const handleDownloadDeliverable = async (docId?: string, filename?: string) => {
    if (!docId) {
      message.error("Document ID is missing from artifact metadata.");
      return;
    }
    setDownloadingDocId(docId);
    try {
      const res = await ragApi.downloadGeneratedDocument(docId, filename || `deliverable_${docId}.pdf`);
      message.success(`Deliverable '${res.filename}' downloaded successfully.`);
    } catch (err: any) {
      message.error(err.message || "Failed downloading generated deliverable artifact.");
    } finally {
      setDownloadingDocId(null);
    }
  };

  // Submit APPROVE action
  const handleApprove = async () => {
    if (!selectedApprovalId) return;
    setActionInProgress(true);
    setActionProgressMessage("Submitting approval and resuming sovereign agent execution...");
    try {
      const res = await approvalsApi.approve(selectedApprovalId, {
        comment: approveComment.trim() || undefined,
      });
      setResolutionResult(res);
      message.success("Approval granted. Deliverable compiled and verified on disk.");
      setApproveModalOpen(false);
      setApproveComment("");
      // Refresh detail and queue
      void loadApprovalDetail(selectedApprovalId);
      void loadApprovals();
      onApprovalResolved?.(selectedApprovalId, res);
    } catch (err: any) {
      if (err.status === 409) {
        message.warning("This approval has already been resolved or expired.");
        void loadApprovalDetail(selectedApprovalId);
        void loadApprovals();
      } else if (err.status === 403) {
        message.error(err.detail || "Access denied: Segregation of duties or department boundary violated.");
      } else {
        message.error(err.detail || err.message || "Failed approving request.");
      }
    } finally {
      setActionInProgress(false);
      setActionProgressMessage("");
    }
  };

  // Submit MODIFY action
  const handleModify = async () => {
    if (!selectedApprovalId) return;
    if (!modifyRevisedText.trim() && !modifyComment.trim()) {
      message.warning("Please provide revised text or modification notes.");
      return;
    }
    setActionInProgress(true);
    setActionProgressMessage("Submitting modifications, initiating agent replan, and compiling revised artifact...");
    try {
      const res = await approvalsApi.modify(selectedApprovalId, {
        revised_text: modifyRevisedText.trim() || undefined,
        comment: modifyComment.trim() || undefined,
      });
      setResolutionResult(res);
      message.success("Modifications submitted. Agent replanned and compiled revised deliverable.");
      setModifyModalOpen(false);
      setModifyComment("");
      // Refresh detail and queue
      void loadApprovalDetail(selectedApprovalId);
      void loadApprovals();
      onApprovalResolved?.(selectedApprovalId, res);
    } catch (err: any) {
      if (err.status === 409) {
        message.warning("This approval has already been resolved or expired.");
        void loadApprovalDetail(selectedApprovalId);
        void loadApprovals();
      } else if (err.status === 403) {
        message.error(err.detail || "Access denied: Segregation of duties or department boundary violated.");
      } else {
        message.error(err.detail || err.message || "Failed submitting modifications.");
      }
    } finally {
      setActionInProgress(false);
      setActionProgressMessage("");
    }
  };

  // Submit REJECT action
  const handleReject = async () => {
    if (!selectedApprovalId) return;
    if (!rejectReason.trim()) {
      message.warning("A rejection reason is mandatory.");
      return;
    }
    setActionInProgress(true);
    setActionProgressMessage("Submitting rejection and halting consequential workflow...");
    try {
      const res = await approvalsApi.reject(selectedApprovalId, {
        reason: rejectReason.trim(),
      });
      setResolutionResult(res);
      message.info("Approval rejected. Consequential workflow halted with zero deliverable publication.");
      setRejectModalOpen(false);
      setRejectReason("");
      // Refresh detail and queue
      void loadApprovalDetail(selectedApprovalId);
      void loadApprovals();
      onApprovalResolved?.(selectedApprovalId, res);
    } catch (err: any) {
      if (err.status === 409) {
        message.warning("This approval has already been resolved or expired.");
        void loadApprovalDetail(selectedApprovalId);
        void loadApprovals();
      } else if (err.status === 403) {
        message.error(err.detail || "Access denied: Segregation of duties or department boundary violated.");
      } else {
        message.error(err.detail || err.message || "Failed rejecting approval.");
      }
    } finally {
      setActionInProgress(false);
      setActionProgressMessage("");
    }
  };

  // Submit RESUME action (for already approved/modified requests)
  const handleResume = async () => {
    if (!selectedApprovalId) return;
    setActionInProgress(true);
    setActionProgressMessage("Resuming execution idempotently...");
    try {
      const res = await approvalsApi.resume(selectedApprovalId, {
        conversation_id: approvalDetail?.conversation_id,
      });
      setResolutionResult(res);
      message.success("Execution resumed successfully.");
      void loadApprovalDetail(selectedApprovalId);
      void loadApprovals();
    } catch (err: any) {
      message.error(err.detail || err.message || "Failed resuming execution.");
    } finally {
      setActionInProgress(false);
      setActionProgressMessage("");
    }
  };

  // Filtered queue items based on search query
  const filteredApprovals = useMemo(() => {
    if (!searchQuery.trim()) return approvals;
    const q = searchQuery.toLowerCase();
    return approvals.filter((a) => {
      const idMatch = a.id?.toLowerCase().includes(q) || a.approval_id?.toLowerCase().includes(q);
      const planMatch = a.plan_id?.toLowerCase().includes(q);
      const reqMatch = a.requester_username?.toLowerCase().includes(q);
      const deptMatch = a.department_name?.toLowerCase().includes(q);
      const sumMatch = a.summary?.toLowerCase().includes(q);
      return idMatch || planMatch || reqMatch || deptMatch || sumMatch;
    });
  }, [approvals, searchQuery]);

  // Queue Statistics (Calculated truthfully from live fetched approvals)
  const stats = useMemo(() => {
    const pendingCount = approvals.filter((a) => a.status === "WAITING_FOR_HUMAN").length;
    const approvedCount = approvals.filter((a) => a.status === "APPROVED").length;
    const modifiedCount = approvals.filter((a) => a.status === "MODIFIED").length;
    const rejectedCount = approvals.filter((a) => a.status === "REJECTED").length;
    const expiredCount = approvals.filter((a) => a.status === "EXPIRED").length;
    return { pendingCount, approvedCount, modifiedCount, rejectedCount, expiredCount };
  }, [approvals]);

  // Status Badge Component Helper
  const renderStatusTag = (status: ApprovalStatusType) => {
    switch (status) {
      case "WAITING_FOR_HUMAN":
        return (
          <Tag color="gold" icon={<ClockCircleOutlined spin />} className="font-mono font-bold text-xs">
            WAITING FOR REVIEW
          </Tag>
        );
      case "APPROVED":
        return (
          <Tag color="success" icon={<CheckCircleOutlined />} className="font-mono font-bold text-xs">
            APPROVED
          </Tag>
        );
      case "MODIFIED":
        return (
          <Tag color="purple" icon={<EditOutlined />} className="font-mono font-bold text-xs">
            MODIFIED & REPLANNED
          </Tag>
        );
      case "REJECTED":
        return (
          <Tag color="error" icon={<CloseCircleOutlined />} className="font-mono font-bold text-xs">
            REJECTED
          </Tag>
        );
      case "EXPIRED":
        return (
          <Tag color="default" icon={<StopOutlined />} className="font-mono text-xs">
            EXPIRED
          </Tag>
        );
      case "FAILED":
        return (
          <Tag color="error" icon={<ExclamationCircleOutlined />} className="font-mono text-xs">
            FAILED
          </Tag>
        );
      default:
        return <Tag>{status}</Tag>;
    }
  };

  // Ant Design Table Columns for Approval Queue
  const columns: ColumnsType<ApprovalItem> = [
    {
      title: "Approval ID",
      dataIndex: "id",
      key: "id",
      width: 140,
      render: (id: string) => (
        <Text copyable className="font-mono text-xs font-semibold text-blue-400">
          {id}
        </Text>
      ),
    },
    {
      title: "Task Summary",
      dataIndex: "summary",
      key: "summary",
      ellipsis: true,
      render: (summary: string, record: ApprovalItem) => (
        <div className="space-y-1">
          <Text strong className="text-slate-100 block text-xs">
            {summary || `Consequential plan ${record.plan_id || ""}`}
          </Text>
          <div className="flex items-center space-x-2 text-[11px] text-slate-400">
            <span>Plan: <span className="font-mono text-slate-300">{record.plan_id || "N/A"}</span></span>
            <span>•</span>
            <span>Format: <Tag className="text-[10px] uppercase">{record.target_format || "DOCX"}</Tag></span>
          </div>
        </div>
      ),
    },
    {
      title: "Requester",
      dataIndex: "requester_username",
      key: "requester_username",
      width: 150,
      render: (username: string, record: ApprovalItem) => (
        <div className="space-y-0.5">
          <div className="flex items-center space-x-1.5 text-xs text-slate-200">
            <UserOutlined className="text-slate-400" />
            <span className="font-semibold">{username || "Operator"}</span>
          </div>
          <div className="text-[11px] text-slate-400">
            {record.department_name || `Dept #${record.department_id || ""}`}
          </div>
        </div>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 170,
      render: (st: ApprovalStatusType) => renderStatusTag(st),
    },
    {
      title: "Requested Time",
      dataIndex: "created_at",
      key: "created_at",
      width: 150,
      responsive: ["md"],
      render: (ts: string) => (
        <div className="text-[11px] text-slate-400 font-mono">
          <div>{new Date(ts).toLocaleDateString()}</div>
          <div className="text-slate-500">{new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
        </div>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      width: 110,
      align: "right",
      render: (_: any, record: ApprovalItem) => (
        <AntButton
          type="primary"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => setSelectedApprovalId(record.id)}
          className="text-xs"
        >
          {record.status === "WAITING_FOR_HUMAN" ? "Review" : "View"}
        </AntButton>
      ),
    },
  ];

  return (
    <div className="aegis-view-stack space-y-6 max-w-[1600px] mx-auto pb-10">
      {/* Header Banner */}
      <section className="bg-[#0d1322]/90 border border-slate-800/80 rounded-xl p-5 sm:px-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center space-x-3.5">
          <div className="h-10 w-10 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-center text-amber-400 shrink-0 shadow-lg shadow-amber-500/5">
            <SafetyCertificateOutlined className="text-xl" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-100">
                {isAuthorizedReviewer ? "Human-in-the-Loop Approvals" : "My Approval Status"}
              </h1>
              {isAuthorizedReviewer && stats.pendingCount > 0 && (
                <Badge count={stats.pendingCount} overflowCount={99} className="font-mono" />
              )}
            </div>
            <p className="text-slate-400 text-xs mt-0.5">
              {isAuthorizedReviewer
                ? "Authoritative evidence review and authorization gateway for consequential AI workflows."
                : "Human-in-the-Loop authorization status for your sovereign AI workflows."}
            </p>
          </div>
        </div>

        {isAuthorizedReviewer && (
          <Space wrap>
            <AntButton
              icon={<ReloadOutlined spin={loading} />}
              onClick={() => void loadApprovals()}
              disabled={loading}
            >
              Refresh
            </AntButton>
          </Space>
        )}
      </section>

      {/* Content Area */}
      {!isAuthorizedReviewer ? (
        <AntCard className="bg-[#0c1220] border-slate-800/80 rounded-xl p-6 text-center shadow-lg">
          <div className="max-w-lg mx-auto space-y-5 py-6">
            <div className="h-14 w-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center mx-auto shadow-inner">
              <SafetyCertificateOutlined className="text-2xl" />
            </div>
            <div className="space-y-2">
              <div className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 text-[11px] font-mono uppercase tracking-wider mb-1">
                <span>Standard Operator Session</span>
              </div>
              <h2 className="text-lg font-bold text-slate-100 uppercase tracking-wider font-mono">
                My Approval Status
              </h2>
              <p className="text-xs text-slate-300 leading-relaxed font-sans">
                You do not have reviewer permissions. Authorization of consequential workflows is restricted to designated supervisors and department leads.
              </p>
              <p className="text-xs text-slate-400 leading-relaxed font-sans">
                You can monitor the real-time HITL lifecycle, execution milestones, and download generated deliverables for your own AI tasks directly in the AI Assistant.
              </p>
            </div>
            {onNavigateToTab && (
              <AntButton
                type="primary"
                size="large"
                icon={<PlayCircleOutlined />}
                onClick={() => onNavigateToTab("chat")}
                className="bg-blue-600 hover:bg-blue-500 text-white font-semibold font-sans px-6"
              >
                Go to AI Assistant
              </AntButton>
            )}
          </div>
        </AntCard>
      ) : (
        <>
          {/* Metric Cards */}
          <Row gutter={[16, 16]}>
            <Col xs={12} sm={8} lg={5}>
              <AntCard className="bg-[#0c1220] border-slate-800/80 rounded-lg">
                <Statistic
                  title={<span className="text-slate-400 text-xs font-semibold uppercase">Pending Review</span>}
                  value={stats.pendingCount}
                  styles={{ content: { color: stats.pendingCount > 0 ? "#faad14" : "#94a3b8", fontWeight: 700 } }}
                  prefix={<ClockCircleOutlined className="mr-1" />}
                />
              </AntCard>
            </Col>
            <Col xs={12} sm={8} lg={5}>
              <AntCard className="bg-[#0c1220] border-slate-800/80 rounded-lg">
                <Statistic
                  title={<span className="text-slate-400 text-xs font-semibold uppercase">Approved</span>}
                  value={stats.approvedCount}
                  styles={{ content: { color: "#52c41a", fontWeight: 700 } }}
                  prefix={<CheckCircleOutlined className="mr-1" />}
                />
              </AntCard>
            </Col>
            <Col xs={12} sm={8} lg={5}>
              <AntCard className="bg-[#0c1220] border-slate-800/80 rounded-lg">
                <Statistic
                  title={<span className="text-slate-400 text-xs font-semibold uppercase">Modified & Replanned</span>}
                  value={stats.modifiedCount}
                  styles={{ content: { color: "#722ed1", fontWeight: 700 } }}
                  prefix={<EditOutlined className="mr-1" />}
                />
              </AntCard>
            </Col>
            <Col xs={12} sm={8} lg={5}>
              <AntCard className="bg-[#0c1220] border-slate-800/80 rounded-lg">
                <Statistic
                  title={<span className="text-slate-400 text-xs font-semibold uppercase">Rejected</span>}
                  value={stats.rejectedCount}
                  styles={{ content: { color: "#ff4d4f", fontWeight: 700 } }}
                  prefix={<CloseCircleOutlined className="mr-1" />}
                />
              </AntCard>
            </Col>
            <Col xs={12} sm={8} lg={4}>
              <AntCard className="bg-[#0c1220] border-slate-800/80 rounded-lg">
                <Statistic
                  title={<span className="text-slate-400 text-xs font-semibold uppercase">Expired</span>}
                  value={stats.expiredCount}
                  styles={{ content: { color: "#64748b", fontWeight: 700 } }}
                  prefix={<StopOutlined className="mr-1" />}
                />
              </AntCard>
            </Col>
          </Row>

          {/* Queue Filter Bar & Search */}
          <div className="bg-[#0d1322]/90 border border-slate-800/80 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <Tabs
              activeKey={statusFilter}
              onChange={(key) => setStatusFilter(key)}
              items={[
                { key: "WAITING_FOR_HUMAN", label: `Awaiting Review (${stats.pendingCount})` },
                { key: "ALL", label: "All Requests" },
                { key: "APPROVED", label: "Approved" },
                { key: "MODIFIED", label: "Modified" },
                { key: "REJECTED", label: "Rejected" },
                { key: "EXPIRED", label: "Expired" },
              ]}
              className="aegis-approval-tabs mb-0"
            />

            <div className="w-full md:w-72">
              <Input
                placeholder="Search by ID, Plan, Requester, or Summary..."
                prefix={<SearchOutlined className="text-slate-500" />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                allowClear
                className="bg-[#05070c] border-slate-800 text-xs"
              />
            </div>
          </div>

          {/* Error Alert */}
          {error && (
            <Alert
              type="error"
              showIcon
              title="Failed to load approvals queue"
              description={error}
              action={
                <AntButton size="small" onClick={() => void loadApprovals()}>
                  Retry
                </AntButton>
              }
            />
          )}

          {/* Approvals Table */}
          <AntCard className="bg-[#0d1322]/90 border-slate-800/80 rounded-xl overflow-hidden p-0">
            <Table<ApprovalItem>
              columns={columns}
              dataSource={filteredApprovals}
              rowKey="id"
              loading={loading}
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                pageSizeOptions: ["10", "20", "50"],
                className: "px-4 py-2",
              }}
              locale={{
                emptyText: (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      <div className="space-y-1 py-6">
                        <Text strong className="text-slate-300 text-sm">
                          No approvals require your attention.
                        </Text>
                        <p className="text-slate-500 text-xs max-w-md mx-auto">
                          When AEGIS pauses a consequential workflow for human review, it will appear in your department queue.
                        </p>
                      </div>
                    }
                  />
                ),
              }}
              rowClassName="hover:bg-slate-800/30 transition-colors cursor-pointer"
              onRow={(record) => ({
                onClick: () => setSelectedApprovalId(record.id),
              })}
            />
          </AntCard>
        </>
      )}

      {/* ========================================================================= */}
      {/* APPROVAL DETAIL DRAWER */}
      {/* ========================================================================= */}
      <Drawer
        title={
          <div className="flex items-center justify-between pr-6">
            <div className="flex items-center space-x-2">
              <SafetyCertificateOutlined className="text-amber-400 text-lg" />
              <span className="text-slate-100 font-bold text-base">Approval Request Review</span>
            </div>
            {approvalDetail && renderStatusTag(approvalDetail.status)}
          </div>
        }
        placement="right"
        size={850}
        open={Boolean(selectedApprovalId)}
        onClose={() => setSelectedApprovalId(null)}
        className="aegis-approval-detail-drawer"
        styles={{
          header: { backgroundColor: "#090e1a", borderBottom: "1px solid #1e293b" },
          body: { backgroundColor: "#070c14", padding: "1.5rem" },
        }}
      >
        {detailLoading ? (
          <div className="space-y-6 py-6">
            <Skeleton active paragraph={{ rows: 4 }} />
            <Skeleton active paragraph={{ rows: 6 }} />
          </div>
        ) : detailError ? (
          <Alert
            type="error"
            showIcon
            title="Error Loading Approval"
            description={detailError}
            action={
              <AntButton size="small" onClick={() => selectedApprovalId && void loadApprovalDetail(selectedApprovalId)}>
                Retry
              </AntButton>
            }
          />
        ) : approvalDetail ? (
          <div className="space-y-6 font-sans">
            {/* Action in progress indicator */}
            {actionInProgress && (
              <Alert
                type="info"
                showIcon
                icon={<LoadingOutlined />}
                title="Processing Human Decision"
                description={actionProgressMessage || "Executing state transition..."}
                className="bg-blue-950/40 border-blue-800 text-blue-200"
              />
            )}

            {/* Resolution Success Banner */}
            {resolutionResult && (
              <Alert
                type={resolutionResult.status === "REJECTED" ? "warning" : "success"}
                showIcon
                title={`Decision Recorded: ${resolutionResult.status}`}
                description={
                  <div className="space-y-2 text-xs">
                    <div>{resolutionResult.message}</div>
                    {resolutionResult.execution?.artifact && (
                      <div className="mt-2 p-2 bg-black/40 border border-emerald-500/30 rounded flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <FileWordOutlined className="text-blue-400 text-base" />
                          <span className="font-semibold text-slate-200">
                            {resolutionResult.execution.artifact.filename}
                          </span>
                        </div>
                        <AntButton
                          type="primary"
                          size="small"
                          icon={<DownloadOutlined />}
                          onClick={() =>
                            handleDownloadDeliverable(
                              resolutionResult.execution?.artifact?.id,
                              resolutionResult.execution?.artifact?.filename
                            )
                          }
                          loading={downloadingDocId === resolutionResult.execution?.artifact?.id}
                        >
                          Download Artifact
                        </AntButton>
                      </div>
                    )}
                  </div>
                }
                className="mb-4"
              />
            )}

            {/* Core Metadata Card */}
            <div className="bg-[#0d1322] border border-slate-800/80 rounded-xl p-5 space-y-4">
              <div className="border-b border-slate-800 pb-3">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Task Objective
                </div>
                <h3 className="text-base font-bold text-slate-100 mt-1">
                  {approvalDetail.summary || `Consequential plan ${approvalDetail.plan_id}`}
                </h3>
              </div>

              <Descriptions size="small" column={{ xs: 1, sm: 2 }} className="aegis-descriptions">
                <Descriptions.Item label="Approval ID">
                  <Text copyable className="font-mono text-xs text-blue-400">
                    {approvalDetail.id}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="Action Type">
                  <Tag color="cyan" className="font-mono text-[11px]">
                    {approvalDetail.action_type}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Plan Reference">
                  <Text className="font-mono text-xs text-slate-300">
                    {approvalDetail.plan_id || "N/A"}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="Workflow Step">
                  <Tag className="font-mono text-[10px]">
                    {approvalDetail.step_id || "Step 5 (HITL Gate)"}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Requester">
                  <span className="font-semibold text-slate-200">
                    {approvalDetail.requester_username || "Operator"}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="Department">
                  <Tag color="blue">
                    {approvalDetail.department_name || `Dept #${approvalDetail.department_id}`}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Requested At">
                  <span className="font-mono text-xs text-slate-400">
                    {new Date(approvalDetail.created_at).toLocaleString()}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="Expiration Policy">
                  {approvalDetail.expires_at ? (
                    <span className="font-mono text-xs text-amber-300">
                      {new Date(approvalDetail.expires_at).toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-slate-500 text-xs">Standard timeout policy</span>
                  )}
                </Descriptions.Item>
              </Descriptions>
            </div>

            {/* Decision History (if already reviewed) */}
            {approvalDetail.status !== "WAITING_FOR_HUMAN" && (
              <div className="bg-[#090e1a] border border-slate-800 rounded-xl p-4 space-y-2">
                <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <HistoryOutlined />
                  <span>Review Audit Trail</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-slate-300 pt-1">
                  <div>
                    <span className="text-slate-500">Reviewer: </span>
                    <span className="font-semibold text-slate-200">
                      {approvalDetail.reviewer_username || "System"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Role: </span>
                    <Tag color="gold" className="text-[10px]">
                      {approvalDetail.reviewer_role?.toUpperCase() || "REVIEWER"}
                    </Tag>
                  </div>
                  <div>
                    <span className="text-slate-500">Reviewed At: </span>
                    <span className="font-mono text-slate-400">
                      {approvalDetail.reviewed_at
                        ? new Date(approvalDetail.reviewed_at).toLocaleString()
                        : "N/A"}
                    </span>
                  </div>
                </div>

                {approvalDetail.rejection_reason && (
                  <div className="mt-3 p-3 bg-rose-950/20 border border-rose-800/40 rounded-lg text-xs text-rose-300">
                    <span className="font-bold block mb-1">Rejection Reason:</span>
                    {approvalDetail.rejection_reason}
                  </div>
                )}

                {approvalDetail.modified_payload && (
                  <div className="mt-3 p-3 bg-purple-950/20 border border-purple-800/40 rounded-lg text-xs text-purple-300 space-y-1">
                    <span className="font-bold block">Reviewer Constraints & Modifications:</span>
                    {approvalDetail.modified_payload.revised_text && (
                      <p className="font-mono text-[11px] whitespace-pre-wrap bg-black/40 p-2 rounded">
                        {approvalDetail.modified_payload.revised_text}
                      </p>
                    )}
                    {approvalDetail.modified_payload.comment && (
                      <p className="italic text-slate-300">
                        Note: {approvalDetail.modified_payload.comment}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Decision Evidence: Technical Findings */}
            {approvalDetail.proposed_payload?.findings && (
              <div className="bg-[#0d1322] border border-slate-800/80 rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                    Extracted Technical Inspection Findings
                  </h4>
                  <Tag color="cyan">Grounded in Knowledge Base</Tag>
                </div>
                <div className="prose prose-invert max-w-none text-xs text-slate-200">
                  <SafeMarkdown content={approvalDetail.proposed_payload.findings} />
                </div>
              </div>
            )}

            {/* Decision Evidence: Calculations & Quantitative Validation */}
            {approvalDetail.proposed_payload?.calculations && (
              <div className="bg-[#0d1322] border border-slate-800/80 rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                    Quantitative Sandbox Calculations & Engineering Metrics
                  </h4>
                  <Tag color="blue">Sandbox Code Verified</Tag>
                </div>
                <div className="bg-[#05070c] border border-slate-800 rounded-lg p-3 font-mono text-xs text-emerald-400 whitespace-pre-wrap">
                  {approvalDetail.proposed_payload.calculations}
                </div>
              </div>
            )}

            {/* Proposed Deliverable Specification */}
            <div className="bg-[#0d1322] border border-slate-800/80 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                  Proposed Industrial Deliverable
                </h4>
                <Tag color="geekblue" className="uppercase font-mono">
                  {approvalDetail.proposed_payload?.target_format || approvalDetail.target_format || "DOCX"}
                </Tag>
              </div>

              {approvalDetail.proposed_payload?.draft_document_text && (
                <div className="space-y-2">
                  <div className="text-[11px] text-slate-400 font-semibold">
                    Draft Synthesized Content Preview:
                  </div>
                  <div className="bg-[#05070c] border border-slate-800 rounded-lg p-3 text-xs text-slate-300 max-h-60 overflow-y-auto">
                    <SafeMarkdown content={approvalDetail.proposed_payload.draft_document_text} />
                  </div>
                </div>
              )}
            </div>

            {/* REVIEWER ACTION BAR */}
            <div className="bg-[#090e1a] border border-slate-800 rounded-xl p-5 sticky bottom-0 shadow-2xl space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-bold text-slate-200">
                    Reviewer Decision Controls
                  </div>
                  <div className="text-[11px] text-slate-400">
                    {approvalDetail.status === "WAITING_FOR_HUMAN"
                      ? "Choose an authoritative action to resolve this pending approval request."
                      : "This approval request has been resolved."}
                  </div>
                </div>

                {approvalDetail.status === "WAITING_FOR_HUMAN" ? (
                  <Space wrap>
                    <AntButton
                      danger
                      icon={<CloseCircleOutlined />}
                      onClick={() => setRejectModalOpen(true)}
                      disabled={!isAuthorizedReviewer || actionInProgress}
                    >
                      Reject
                    </AntButton>

                    <AntButton
                      icon={<EditOutlined />}
                      onClick={() => setModifyModalOpen(true)}
                      disabled={!isAuthorizedReviewer || actionInProgress}
                      className="text-purple-400 border-purple-800/60 hover:border-purple-600"
                    >
                      Modify & Replan
                    </AntButton>

                    <AntButton
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      onClick={() => setApproveModalOpen(true)}
                      disabled={!isAuthorizedReviewer || actionInProgress}
                      className="bg-emerald-600 hover:bg-emerald-500 border-none font-semibold"
                    >
                      Approve & Execute
                    </AntButton>
                  </Space>
                ) : (
                  <Space wrap>
                    {(approvalDetail.status === "APPROVED" || approvalDetail.status === "MODIFIED") && (
                      <AntButton
                        type="default"
                        icon={<PlayCircleOutlined />}
                        onClick={handleResume}
                        disabled={actionInProgress}
                      >
                        Resume Execution
                      </AntButton>
                    )}
                  </Space>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </Drawer>

      {/* ========================================================================= */}
      {/* 1. APPROVE CONFIRMATION MODAL */}
      {/* ========================================================================= */}
      <Modal
        title={
          <div className="flex items-center space-x-2 text-emerald-400 font-bold">
            <CheckCircleOutlined />
            <span>Approve & Authorize Task Execution</span>
          </div>
        }
        open={approveModalOpen}
        onCancel={() => setApproveModalOpen(false)}
        onOk={handleApprove}
        okText="Confirm & Resume Execution"
        okButtonProps={{ className: "bg-emerald-600 hover:bg-emerald-500 border-none", loading: actionInProgress }}
        cancelButtonProps={{ disabled: actionInProgress }}
        className="aegis-decision-modal"
      >
        <div className="space-y-4 py-3 text-xs text-slate-300">
          <p className="leading-relaxed">
            Approving this request authorizes AEGIS to resume the consequential workflow and compile the final industrial deliverable (<span className="font-mono text-slate-100">{approvalDetail?.target_format?.toUpperCase() || "DOCX"}</span>).
          </p>

          <div className="space-y-1.5">
            <label className="text-slate-400 font-semibold block">Optional Reviewer Notes / Sign-Off Comment:</label>
            <TextArea
              rows={3}
              maxLength={1000}
              showCount
              value={approveComment}
              onChange={(e) => setApproveComment(e.target.value)}
              placeholder="e.g., Reviewed cooling tower efficiency calculations. Approved for operations note compilation."
              className="bg-[#05070c] border-slate-800 text-slate-200 text-xs"
            />
          </div>
        </div>
      </Modal>

      {/* ========================================================================= */}
      {/* 2. MODIFY & REPLAN MODAL */}
      {/* ========================================================================= */}
      <Modal
        title={
          <div className="flex items-center space-x-2 text-purple-400 font-bold">
            <EditOutlined />
            <span>Modify Request & Trigger Agent Replanning</span>
          </div>
        }
        open={modifyModalOpen}
        onCancel={() => setModifyModalOpen(false)}
        onOk={handleModify}
        okText="Submit Constraints & Replan"
        okButtonProps={{ className: "bg-purple-600 hover:bg-purple-500 border-none", loading: actionInProgress }}
        cancelButtonProps={{ disabled: actionInProgress }}
        width={700}
        className="aegis-decision-modal"
      >
        <div className="space-y-4 py-3 text-xs text-slate-300">
          <Alert
            type="info"
            showIcon
            title="Replanning Constraint Architecture"
            description="Your revisions and corrective notes are injected as authoritative planning constraints into the sovereign agent. The agent will replan remaining steps, synthesize revised content, and compile verified deliverables."
            className="bg-purple-950/30 border-purple-800/40 text-purple-200"
          />

          <div className="space-y-1.5">
            <label className="text-slate-300 font-semibold block">
              Revised Content / Specific Technical Modifications (Max 5,000 chars):
            </label>
            <TextArea
              rows={6}
              maxLength={5000}
              showCount
              value={modifyRevisedText}
              onChange={(e) => setModifyRevisedText(e.target.value)}
              placeholder="Enter corrective notes, modified parameters, or revised text sections..."
              className="bg-[#05070c] border-slate-800 text-slate-200 font-mono text-xs"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-slate-300 font-semibold block">
              Reviewer Rationale Comment (Max 1,000 chars):
            </label>
            <Input
              maxLength={1000}
              value={modifyComment}
              onChange={(e) => setModifyComment(e.target.value)}
              placeholder="e.g., Updated vibration threshold limit per Q3 plant maintenance memo."
              className="bg-[#05070c] border-slate-800 text-slate-200 text-xs"
            />
          </div>
        </div>
      </Modal>

      {/* ========================================================================= */}
      {/* 3. REJECT CONFIRMATION MODAL */}
      {/* ========================================================================= */}
      <Modal
        title={
          <div className="flex items-center space-x-2 text-rose-400 font-bold">
            <CloseCircleOutlined />
            <span>Reject Consequential Task Request</span>
          </div>
        }
        open={rejectModalOpen}
        onCancel={() => setRejectModalOpen(false)}
        onOk={handleReject}
        okText="Confirm Rejection & Halt Workflow"
        okButtonProps={{ danger: true, loading: actionInProgress }}
        cancelButtonProps={{ disabled: actionInProgress }}
        className="aegis-decision-modal"
      >
        <div className="space-y-4 py-3 text-xs text-slate-300">
          <Alert
            type="warning"
            showIcon
            title="Workflow Termination"
            description="Rejecting this request will permanently halt the consequential workflow. No deliverable documents will be compiled or published to organizational workspaces."
            className="bg-rose-950/30 border-rose-800/40 text-rose-300"
          />

          <div className="space-y-1.5">
            <label className="text-slate-300 font-semibold block">
              Mandatory Rejection Rationale <span className="text-rose-400">*</span> (1–1,000 chars):
            </label>
            <TextArea
              rows={4}
              maxLength={1000}
              showCount
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Please provide explicit reason for rejection..."
              className="bg-[#05070c] border-slate-800 text-slate-200 text-xs"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
