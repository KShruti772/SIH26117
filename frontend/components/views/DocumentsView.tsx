"use client";

import React, { useState, useEffect } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Input,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Steps,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload
} from "antd";
import {
  CodeOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileAddOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileTextOutlined,
  FileWordOutlined,
  GlobalOutlined,
  LockOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  ShareAltOutlined,
  TableOutlined,
  TeamOutlined,
  UploadOutlined,
  UserOutlined
} from "@ant-design/icons";
import { ragApi, DocumentInfo, GeneratedDocument, DocumentPermission } from "../../lib/api/rag";
import { authApi, Department, User } from "../../lib/api/auth";
import { env } from "../../lib/config/env";
import { getToken } from "../../lib/security/token";

const { Dragger } = Upload;

interface Props {
  documents: DocumentInfo[];
  loading: boolean;
  error: string | null;
  file: File | null;
  uploading: boolean;
  uploadProgressStage?: string | null;
  uploadSuccess: string | null;
  uploadError: string | null;
  search: string;
  setSearch: (v: string) => void;
  status: string;
  setStatus: (v: string) => void;
  type: string;
  setType: (v: string) => void;
  onFile: (f: File) => void;
  onUpload: (visibility?: string) => void;
  onAnalyze?: (document: DocumentInfo) => void;
  currentUser?: User | null;
  onRefresh: () => void;
  onReindex: (id: string) => void;
  onDelete: (id: string, name: string) => void;
  reindexing: string | null;
  deleting: string | null;
}

export default function DocumentsView(p: Props) {
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState<string>("source");
  const [generatedDocs, setGeneratedDocs] = useState<GeneratedDocument[]>([]);
  const [genLoading, setGenLoading] = useState<boolean>(false);
  const [genError, setGenError] = useState<string | null>(null);

  // Ingestion Visibility State
  const [uploadVisibility, setUploadVisibility] = useState<string>("PRIVATE");

  // Generate Report Modal States
  const [isGenerateModalOpen, setIsGenerateModalOpen] = useState(false);
  const [reportTitle, setReportTitle] = useState("");
  const [reportTopic, setReportTopic] = useState("");
  const [reportFormat, setReportFormat] = useState<string>("pdf");
  const [selectedDocForReport, setSelectedDocForReport] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  // Share & Access Control Modal States
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [selectedShareDoc, setSelectedShareDoc] = useState<DocumentInfo | null>(null);
  const [permissionsList, setPermissionsList] = useState<DocumentPermission[]>([]);
  const [permissionsLoading, setPermissionsLoading] = useState(false);
  const [departmentsList, setDepartmentsList] = useState<Department[]>([]);
  const [shareTargetType, setShareTargetType] = useState<"department" | "user">("department");
  const [shareTargetUserId, setShareTargetUserId] = useState<number | undefined>(undefined);
  const [shareTargetDeptId, setShareTargetDeptId] = useState<number | undefined>(undefined);
  const [sharePermissionLevel, setSharePermissionLevel] = useState<string>("READ");
  const [grantingShare, setGrantingShare] = useState(false);
  const [updatingVisibility, setUpdatingVisibility] = useState(false);

  const loadGeneratedDocuments = async () => {
    setGenLoading(true);
    setGenError(null);
    try {
      const data = await ragApi.listGeneratedDocuments();
      setGeneratedDocs(data);
    } catch (err: any) {
      setGenError(err.message || "Failed loading generated reports.");
    } finally {
      setGenLoading(false);
    }
  };

  const loadDepartments = async () => {
    try {
      const depts = await authApi.listDepartments();
      setDepartmentsList(depts);
    } catch {
      // Non-critical fallback
    }
  };

  useEffect(() => {
    loadGeneratedDocuments();
    loadDepartments();
  }, []);

  const handleDownloadGenerated = async (doc: GeneratedDocument) => {
    try {
      const token = getToken();
      const res = await fetch(`${env.apiUrl}/documents/generated/${doc.id}/download`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      if (!res.ok) throw new Error("Download request failed.");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e.message || "Failed to download document.");
    }
  };

  const handleDownloadSource = async (doc: DocumentInfo) => {
    try {
      const token = getToken();
      const res = await fetch(`${env.apiUrl}/documents/${doc.id}/download`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || "Download request failed.");
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e.message || "Failed to download document.");
    }
  };

  const handleOpenSource = async (doc: DocumentInfo) => {
    try {
      const token = getToken();
      const res = await fetch(`${env.apiUrl}/documents/${doc.id}/preview`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || "Preview request failed.");
      const url = window.URL.createObjectURL(await res.blob());
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e: any) {
      message.error(e.message || "Failed to open document.");
    }
  };

  const handleDeleteGenerated = async (id: string) => {
    try {
      await ragApi.deleteGeneratedDocument(id);
      message.success("Report deleted.");
      loadGeneratedDocuments();
    } catch (e: any) {
      message.error(e.message || "Failed to delete report.");
    }
  };

  const handleGenerateSubmit = async () => {
    if (!reportTitle.trim()) {
      message.warning("Please enter a report title.");
      return;
    }
    setGenerating(true);
    try {
      await ragApi.generateReport({
        title: reportTitle.trim(),
        topic: reportTopic.trim() || reportTitle.trim(),
        format: reportFormat,
        document_id: selectedDocForReport || undefined
      });
      message.success(`Report '${reportTitle}' generated successfully!`);
      setIsGenerateModalOpen(false);
      setReportTitle("");
      setReportTopic("");
      loadGeneratedDocuments();
      setActiveTab("generated");
    } catch (err: any) {
      message.error(err.message || "Failed generating report.");
    } finally {
      setGenerating(false);
    }
  };

  // Open Share & Permissions Modal
  const openShareModal = async (doc: DocumentInfo) => {
    setSelectedShareDoc(doc);
    setIsShareModalOpen(true);
    setPermissionsLoading(true);
    try {
      const perms = await ragApi.listPermissions(doc.id);
      setPermissionsList(perms);
    } catch (err: any) {
      message.error(err.message || "Failed loading document permissions.");
      setPermissionsList([]);
    } finally {
      setPermissionsLoading(false);
    }
  };

  const handleGrantShare = async () => {
    if (!selectedShareDoc) return;
    if (shareTargetType === "department" && !shareTargetDeptId) {
      message.warning("Please select a target department.");
      return;
    }
    if (shareTargetType === "user" && !shareTargetUserId) {
      message.warning("Please enter a target user ID.");
      return;
    }

    setGrantingShare(true);
    try {
      await ragApi.shareDocument(selectedShareDoc.id, {
        department_id: shareTargetType === "department" ? shareTargetDeptId : undefined,
        user_id: shareTargetType === "user" ? shareTargetUserId : undefined,
        permission: sharePermissionLevel
      });
      message.success("Access permission granted successfully.");
      const updatedPerms = await ragApi.listPermissions(selectedShareDoc.id);
      setPermissionsList(updatedPerms);
      setShareTargetUserId(undefined);
    } catch (err: any) {
      message.error(err.message || "Failed to grant access permission.");
    } finally {
      setGrantingShare(false);
    }
  };

  const handleRevokeShare = async (permId: number) => {
    if (!selectedShareDoc) return;
    try {
      await ragApi.revokePermission(selectedShareDoc.id, permId);
      message.success("Permission revoked.");
      const updatedPerms = await ragApi.listPermissions(selectedShareDoc.id);
      setPermissionsList(updatedPerms);
    } catch (err: any) {
      message.error(err.message || "Failed to revoke permission.");
    }
  };

  const handleUpdateVisibility = async (newVisibility: string) => {
    if (!selectedShareDoc) return;
    setUpdatingVisibility(true);
    try {
      await ragApi.updateVisibility(selectedShareDoc.id, newVisibility);
      message.success(`Document visibility updated to ${newVisibility}.`);
      setSelectedShareDoc({ ...selectedShareDoc, visibility: newVisibility });
      p.onRefresh();
    } catch (err: any) {
      message.error(err.message || "Failed to update visibility policy.");
    } finally {
      setUpdatingVisibility(false);
    }
  };

  const types = [
    ...new Set(
      p.documents
        .map((d) => (d.filename.split(".").pop() || "").toUpperCase())
        .filter(Boolean)
    )
  ];

  const sourceRows = p.documents.filter(
    (d) =>
      d.filename.toLowerCase().includes(p.search.toLowerCase()) &&
      (!p.type || (d.filename.split(".").pop() || "").toUpperCase() === p.type) &&
      (!p.status || d.status?.toLowerCase().includes(p.status.toLowerCase()))
  );

  const getFormatIcon = (filename: string, category?: string) => {
    const ext = (filename.split(".").pop() || "").toLowerCase();
    if (ext === "pdf") return <FilePdfOutlined className="text-red-400 text-base" />;
    if (["docx", "doc", "odt", "rtf"].includes(ext)) return <FileWordOutlined className="text-blue-400 text-base" />;
    if (["xlsx", "xls", "csv", "tsv"].includes(ext) || category === "spreadsheet") return <TableOutlined className="text-emerald-400 text-base" />;
    if (["pptx", "ppt", "odp"].includes(ext) || category === "presentation") return <FilePptOutlined className="text-amber-400 text-base" />;
    if (["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif"].includes(ext) || category === "image") return <PictureOutlined className="text-purple-400 text-base" />;
    if (["py", "js", "ts", "java", "c", "cpp", "sql", "sh", "json", "yaml", "xml"].includes(ext) || category === "code") return <CodeOutlined className="text-cyan-400 text-base" />;
    return <FileTextOutlined className="text-slate-400 text-base" />;
  };

  const getVisibilityTag = (visibility?: string) => {
    const vis = visibility?.toUpperCase();
    if (vis === "ORGANIZATION") {
      return (
        <Tag color="green" className="font-mono text-[10px] font-bold uppercase flex items-center gap-1 w-fit">
          <GlobalOutlined /> Org-Wide
        </Tag>
      );
    }
    if (vis === "DEPARTMENT") {
      return (
        <Tag color="blue" className="font-mono text-[10px] font-bold uppercase flex items-center gap-1 w-fit">
          <TeamOutlined /> Dept
        </Tag>
      );
    }
    if (vis === "SHARED") {
      return <Tag color="orange" className="font-mono text-[10px] font-bold uppercase flex items-center gap-1 w-fit"><ShareAltOutlined /> Shared</Tag>;
    }
    if (vis === "PRIVATE") {
      return <Tag color="purple" className="font-mono text-[10px] font-bold uppercase flex items-center gap-1 w-fit"><LockOutlined /> Private</Tag>;
    }
    return (
      <Tag color="default" className="font-mono text-[10px] font-bold uppercase flex items-center gap-1 w-fit">
        Access not reported
      </Tag>
    );
  };

  const sourceColumns = [
    {
      title: "Document",
      dataIndex: "filename",
      render: (v: string, d: DocumentInfo) => (
        <div className="flex items-center space-x-2.5">
          {getFormatIcon(v, d.category)}
          <div>
            <Typography.Text strong className="text-slate-100 block">
              {v}
            </Typography.Text>
            <span className="text-[11px] text-slate-500 font-mono">
              ID: {d.id ? d.id.slice(0, 16) + "..." : "—"}
            </span>
          </div>
        </div>
      )
    },
    {
      title: "Owner",
      key: "owner_department",
      render: (_: any, d: DocumentInfo) => (
        <div>
          <div className="flex items-center space-x-1.5">
            <TeamOutlined className="text-blue-400 text-xs" />
            <span className="text-xs font-semibold text-slate-200">{d.owner_username || "Not reported"}</span>
          </div>
          <div className="flex items-center space-x-1 text-[11px] text-slate-400 font-mono mt-0.5">
            <UserOutlined className="text-[10px]" />
            <span>Authenticated owner</span>
          </div>
        </div>
      )
    },
    {
      title: "Department",
      key: "department",
      render: (_: string, d: DocumentInfo) => <span className="text-xs text-slate-300">{d.owner_department_name || "Not reported"}</span>
    },
    {
      title: "Access",
      dataIndex: "visibility",
      render: (v: string) => getVisibilityTag(v)
    },
    {
      title: "Status",
      dataIndex: "status",
      render: (v: string) => {
        const isError = (v || "ready").match(/fail|error/i);
        const isProcessing = (v || "").match(/process|ingest/i);
        const color = isError ? "error" : isProcessing ? "processing" : "success";
        return (
          <Tag color={color} className="font-bold text-[10px] uppercase font-mono">
            {v ? v.toUpperCase() : "NOT REPORTED"}
          </Tag>
        );
      }
    },
    {
      title: "Updated",
      dataIndex: "uploaded_at",
      render: (v: number | string) => <span className="font-mono text-xs text-slate-400">{v ? new Date(typeof v === "number" ? v * 1000 : v).toLocaleString() : "Not reported"}</span>
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, d: DocumentInfo) => (
        <Space size="small">
          <Tooltip title="Open document">
            <Button size="small" type="text" onClick={() => handleOpenSource(d)} className="text-slate-300 hover:text-blue-400">Open</Button>
          </Tooltip>
          <Tooltip title="Analyze document">
            <Button size="small" type="text" onClick={() => p.onAnalyze?.(d)} className="text-slate-300 hover:text-blue-400">Analyze</Button>
          </Tooltip>
          {d.can_download && <Tooltip title="Download Source File">
            <Button
              size="small"
              type="text"
              icon={<DownloadOutlined />}
              onClick={() => handleDownloadSource(d)}
              className="text-slate-300 hover:text-blue-400"
            />
          </Tooltip>}
          {d.can_share && <Tooltip title="Manage Access & Permissions">
            <Button
              size="small"
              type="text"
              icon={<ShareAltOutlined />}
              onClick={() => openShareModal(d)}
              className="text-slate-300 hover:text-indigo-400"
            />
          </Tooltip>}
          {d.can_delete && <Tooltip title="Delete Document">
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              loading={p.deleting === d.id}
              onClick={() => p.onDelete(d.id, d.filename)}
            />
          </Tooltip>}
        </Space>
      )
    }
  ];

  const generatedColumns = [
    {
      title: "Generated Report",
      dataIndex: "title",
      render: (v: string, d: GeneratedDocument) => (
        <div className="flex items-center space-x-2.5">
          {d.format === "docx" ? (
            <FileWordOutlined className="text-blue-500 text-lg" />
          ) : (
            <FilePdfOutlined className="text-red-400 text-lg" />
          )}
          <div>
            <Typography.Text strong className="text-slate-100 block">
              {v || d.filename}
            </Typography.Text>
            <span className="text-[11px] text-slate-500 font-mono">
              {d.filename} · {d.file_size ? `${(d.file_size / 1024).toFixed(1)} KB` : ""}
            </span>
          </div>
        </div>
      )
    },
    {
      title: "Department & Owner",
      key: "owner_department",
      render: (_: any, d: GeneratedDocument) => (
        <div>
          <div className="flex items-center space-x-1.5">
            <TeamOutlined className="text-blue-400 text-xs" />
            <span className="text-xs font-semibold text-slate-200">
              {d.owner_department_name || "Not reported"}
            </span>
          </div>
          <div className="flex items-center space-x-1 text-[11px] text-slate-400 font-mono mt-0.5">
            <UserOutlined className="text-[10px]" />
            <span>{d.owner_username || "Not reported"}</span>
          </div>
        </div>
      )
    },
    {
      title: "Format",
      dataIndex: "format",
      render: (v: string) => (
        <Tag color={v === "docx" ? "blue" : "red"} className="font-mono text-xs uppercase font-bold">
          {v}
        </Tag>
      )
    },
    {
      title: "Created At",
      dataIndex: "created_at",
      render: (v: string) => (
        <span className="font-mono text-xs text-slate-400">
          {v ? new Date(v).toLocaleString() : "—"}
        </span>
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, d: GeneratedDocument) => (
        <Space size="small">
          <Button
            size="small"
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => handleDownloadGenerated(d)}
            className="bg-blue-600 hover:bg-blue-500 text-xs font-semibold"
          >
            Download
          </Button>
          <Button
            size="small"
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteGenerated(d.id)}
          />
        </Space>
      )
    }
  ];

  return (
    <div className="aegis-view-stack space-y-6">
      {/* Header */}
      <section className="aegis-view-heading flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <Typography.Title level={2} className="!mb-1 !text-slate-100 flex items-center space-x-2.5">
            <FileTextOutlined className="text-blue-400" />
            <span>Documents</span>
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Manage authorized documents, indexing, access policies, and sharing.
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Button
            type="primary"
            icon={<RobotOutlined />}
            onClick={() => setIsGenerateModalOpen(true)}
            className="bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold"
          >
            Generate Grounded Report
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { p.onRefresh(); loadGeneratedDocuments(); }}>
            Refresh
          </Button>
        </Space>
      </section>

      {/* Overview Statistics */}
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card className="aegis-panel-card bg-[#080d1a] border-slate-800">
            <Statistic
              title={<span className="text-slate-400 text-xs uppercase font-bold">Accessible Documents</span>}
              value={p.documents.length}
              styles={{ content: { color: "#38bdf8", fontWeight: 700 } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="aegis-panel-card bg-[#080d1a] border-slate-800">
            <Statistic
              title={<span className="text-slate-400 text-xs uppercase font-bold">Vector Chunks</span>}
              value={p.documents.every((d) => d.chunk_count != null || d.chunks != null) ? p.documents.reduce((acc, d) => acc + (d.chunk_count ?? d.chunks ?? 0), 0) : "Not reported"}
              styles={{ content: { color: "#34d399", fontWeight: 700 } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="aegis-panel-card bg-[#080d1a] border-slate-800">
            <Statistic
              title={<span className="text-slate-400 text-xs uppercase font-bold">Generated Reports</span>}
              value={generatedDocs.length}
              styles={{ content: { color: "#a78bfa", fontWeight: 700 } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="aegis-panel-card bg-[#080d1a] border-slate-800">
            <Statistic
              title={<span className="text-slate-400 text-xs uppercase font-bold">Access Control</span>}
              value="Multi-Tenant RBAC"
              styles={{ content: { color: "#fbbf24", fontWeight: 700, fontSize: "1.1rem" } }}
            />
          </Card>
        </Col>
      </Row>

      {/* Main Tabs */}
      <Card className="aegis-panel-card bg-[#080d1a] border-slate-800 shadow-md">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: "source",
              label: (
                <span className="font-semibold px-2">
                  <FileTextOutlined className="mr-1.5" />
                  Source Documents ({p.documents.length})
                </span>
              ),
              children: (
                <Row gutter={[20, 20]} className="pt-2">
                  {/* Upload & Ingestion Policy Card */}
                  <Col xs={24} lg={8}>
                    <Card
                      title={
                        <Space>
                          <UploadOutlined className="text-blue-400" />
                          <span className="text-slate-200">Ingest New Document</span>
                        </Space>
                      }
                      className="bg-[#050811] border-slate-800"
                    >
                      <Steps
                        size="small"
                        current={p.uploadProgressStage === "DOCUMENT UPLOAD" ? 0 : p.uploadProgressStage === "TEXT EXTRACTION" ? 1 : p.uploadProgressStage === "EMBEDDING" || p.uploadProgressStage === "CHROMADB COMMIT" ? 3 : p.file ? 1 : 0}
                        items={[{ title: "Select file" }, { title: "Document info" }, { title: "Access policy" }, { title: "Upload & index" }]}
                        className="mb-4"
                      />
                      <Dragger
                        multiple={false}
                        showUploadList={false}
                        beforeUpload={(file) => {
                          p.onFile(file);
                          return false;
                        }}
                        className="bg-[#080d1a] border-slate-800 hover:border-blue-500/50 p-4"
                      >
                        <p className="ant-upload-drag-icon text-blue-400">
                          <FileAddOutlined className="text-3xl" />
                        </p>
                        <p className="text-slate-200 text-sm font-semibold mb-1">
                          Click or drag file to ingest
                        </p>
                        <p className="text-slate-400 text-xs">
                          PDF, Word, Excel, CSV, PowerPoint, Images, Code
                        </p>
                        <p className="text-slate-500 text-[11px] mt-1">
                          100% Sovereign · Secure Deduplication
                        </p>
                      </Dragger>

                      {/* Visibility Policy Selector */}
                      <div className="mt-4 p-3 bg-[#080d1a] border border-slate-800 rounded-lg">
                        <label className="block text-xs font-semibold text-slate-300 mb-2">
                          Document Access Policy:
                        </label>
                        <Radio.Group
                          value={uploadVisibility}
                          onChange={(e) => setUploadVisibility(e.target.value)}
                          className="w-full space-y-1.5"
                        >
                          <Radio value="PRIVATE" className="text-slate-300 text-xs block">
                            <span className="font-semibold text-purple-400">PRIVATE:</span> Only you and explicitly shared users/teams
                          </Radio>
                          <Radio value="DEPARTMENT" className="text-slate-300 text-xs block">
                            <span className="font-semibold text-blue-400">DEPARTMENT:</span> All members in your department
                          </Radio>
                          <Radio value="SHARED" className="text-slate-300 text-xs block">
                            <span className="font-semibold text-orange-400">SHARED:</span> Only explicitly authorized users or departments
                          </Radio>
                          <Radio value="ORGANIZATION" className="text-slate-300 text-xs block">
                            <span className="font-semibold text-emerald-400">ORGANIZATION:</span> All enterprise members
                          </Radio>
                        </Radio.Group>
                      </div>

                      <div className="mt-3 text-[11px] text-slate-400">
                        Uploader department: <span className="font-semibold text-slate-200">{p.currentUser?.department_name || "Not reported by account"}</span>
                      </div>

                      {p.file && (
                        <div className="mt-4 p-3 bg-[#080d1a] border border-slate-800 rounded-lg flex items-center justify-between">
                          <div className="truncate pr-2 text-xs text-slate-200 font-semibold">
                            {p.file.name}
                          </div>
                          <Button
                            type="primary"
                            size="small"
                            loading={p.uploading}
                            onClick={() => p.onUpload(uploadVisibility)}
                            className="bg-blue-600 font-semibold"
                          >
                            Index Document
                          </Button>
                        </div>
                      )}

                      {p.uploadSuccess && (
                        <Alert className="mt-4" type="success" showIcon title={p.uploadSuccess} />
                      )}
                      {p.uploadError && (
                        <Alert
                          className="mt-4"
                          type="error"
                          showIcon
                          title="Ingestion Failed"
                          description={p.uploadError}
                        />
                      )}
                    </Card>
                  </Col>

                  {/* Document Table */}
                  <Col xs={24} lg={16}>
                    <Space wrap orientation="horizontal" className="mb-4 w-full justify-between">
                      <Input
                        prefix={<SearchOutlined />}
                        placeholder="Search indexed documents…"
                        value={p.search}
                        onChange={(e) => p.setSearch(e.target.value)}
                        allowClear
                        style={{ width: 220 }}
                        className="bg-[#050811] border-slate-700"
                      />
                      <Space wrap>
                        <Select
                          placeholder="Status"
                          allowClear
                          value={p.status || undefined}
                          onChange={(v) => p.setStatus(v || "")}
                          style={{ width: 120 }}
                          options={[
                            { value: "indexed", label: "Indexed" },
                            { value: "processing", label: "Processing" },
                            { value: "failed", label: "Failed" }
                          ]}
                        />
                        <Select
                          placeholder="File type"
                          allowClear
                          value={p.type || undefined}
                          onChange={(v) => p.setType(v || "")}
                          style={{ width: 110 }}
                          options={types.map((v) => ({ value: v, label: v }))}
                        />
                      </Space>
                    </Space>

                    <Table
                      rowKey="id"
                      loading={p.loading}
                      columns={sourceColumns}
                      dataSource={sourceRows}
                      scroll={{ x: 800 }}
                      pagination={{ pageSize: 6 }}
                      locale={{
                        emptyText: (
                          <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description="No authorized documents yet."
                          />
                        )
                      }}
                    />
                  </Col>
                </Row>
              )
            },
            {
              key: "generated",
              label: (
                <span className="font-semibold px-2">
                  <RobotOutlined className="mr-1.5" />
                  Generated Intelligence Reports ({generatedDocs.length})
                </span>
              ),
              children: (
                <div className="pt-2">
                  {genError && (
                    <Alert type="error" showIcon title="Failed loading generated reports" description={genError} className="mb-4" />
                  )}
                  <Table
                    rowKey="id"
                    loading={genLoading}
                    columns={generatedColumns}
                    dataSource={generatedDocs}
                    scroll={{ x: 700 }}
                    pagination={{ pageSize: 6 }}
                    locale={{
                      emptyText: (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description="No intelligence reports generated yet. Click 'Generate Grounded Report' above."
                        />
                      )
                    }}
                  />
                </div>
              )
            }
          ]}
        />
      </Card>

      {/* Share & Access Control Modal */}
      <Modal
        title={
          <Space>
            <ShareAltOutlined className="text-indigo-400" />
            <span>Document Access & Sharing Policy</span>
          </Space>
        }
        open={isShareModalOpen}
        onCancel={() => setIsShareModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setIsShareModalOpen(false)}>
            Close
          </Button>
        ]}
        width={680}
      >
        {selectedShareDoc && (
          <div className="space-y-5 py-2">
            {/* Header info */}
            <div className="p-3 bg-[#080d1a] border border-slate-800 rounded-lg">
              <Typography.Text strong className="text-slate-100 block text-sm mb-1">
                {selectedShareDoc.filename}
              </Typography.Text>
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <span>Owner: <strong className="text-slate-200">{selectedShareDoc.owner_username || "Not reported"}</strong></span>
                <span>Department: <strong className="text-slate-200">{selectedShareDoc.owner_department_name || "Not reported"}</strong></span>
                <span>Current Policy: {getVisibilityTag(selectedShareDoc.visibility)}</span>
              </div>
            </div>

            {/* Visibility Policy Change */}
            <div className="p-3 bg-[#050811] border border-slate-800 rounded-lg">
              <label className="block text-xs font-semibold text-slate-300 mb-2">
                Change Visibility Policy:
              </label>
              <div className="flex items-center gap-3">
                <Select
                  value={selectedShareDoc.visibility || "PRIVATE"}
                  onChange={(v) => handleUpdateVisibility(v)}
                  loading={updatingVisibility}
                  className="flex-1"
                  options={[
                    { value: "PRIVATE", label: "PRIVATE — Only Owner & Explicit Shares" },
                    { value: "DEPARTMENT", label: "DEPARTMENT — Entire Department" },
                    { value: "ORGANIZATION", label: "ORGANIZATION — All Enterprise Users" }
                  ]}
                />
              </div>
            </div>

            {/* Grant Access Section */}
            <div className="p-3 bg-[#050811] border border-slate-800 rounded-lg space-y-3">
              <Typography.Text strong className="text-xs text-slate-300 block">
                Grant Explicit Access:
              </Typography.Text>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <Select
                  value={shareTargetType}
                  onChange={(v) => setShareTargetType(v)}
                  options={[
                    { value: "department", label: "Department Grant" },
                    { value: "user", label: "User Grant (ID)" }
                  ]}
                />
                {shareTargetType === "department" ? (
                  <Select
                    placeholder="Select Department"
                    value={shareTargetDeptId}
                    onChange={(v) => setShareTargetDeptId(v)}
                    options={departmentsList.map((d) => ({
                      value: d.id,
                      label: `${d.name} (${d.code})`
                    }))}
                  />
                ) : (
                  <InputNumber
                    placeholder="Target User ID"
                    value={shareTargetUserId}
                    onChange={(v) => setShareTargetUserId(v ?? undefined)}
                    className="w-full"
                    min={1}
                  />
                )}
                <Select
                  value={sharePermissionLevel}
                  onChange={(v) => setSharePermissionLevel(v)}
                  options={[
                    { value: "READ", label: "READ (Preview & Search)" },
                    { value: "DOWNLOAD", label: "DOWNLOAD (Download file)" },
                    { value: "USE_IN_RAG", label: "USE_IN_RAG (Knowledge QA)" },
                    { value: "MANAGE", label: "MANAGE (Share & Visibility)" },
                    { value: "FULL_CONTROL", label: "FULL CONTROL (Admin/Delete)" }
                  ]}
                />
              </div>
              <Button
                type="primary"
                size="small"
                loading={grantingShare}
                onClick={handleGrantShare}
                className="bg-indigo-600 font-semibold"
              >
                Grant Access
              </Button>
            </div>

            {/* Active Permissions List */}
            <div>
              <Typography.Text strong className="text-xs text-slate-300 block mb-2">
                Active Explicit Access Grants ({permissionsList.length})
              </Typography.Text>
              <Table
                rowKey="id"
                size="small"
                loading={permissionsLoading}
                dataSource={permissionsList}
                pagination={false}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="No explicit shares. Visibility policy applies."
                    />
                  )
                }}
                columns={[
                  {
                    title: "Recipient",
                    key: "recipient",
                    render: (_: any, r: DocumentPermission) => {
                      if (r.department_id) {
                        return (
                          <span className="text-xs text-blue-400 font-semibold flex items-center gap-1">
                            <TeamOutlined /> Dept: {r.department_name || `Dept #${r.department_id}`}
                          </span>
                        );
                      }
                      return (
                        <span className="text-xs text-purple-400 font-semibold flex items-center gap-1">
                          <UserOutlined /> User: {r.user_name || `User #${r.user_id}`}
                        </span>
                      );
                    }
                  },
                  {
                    title: "Permission",
                    dataIndex: "permission",
                    render: (v: string) => (
                      <Tag color="cyan" className="font-mono text-[10px] font-bold">
                        {v}
                      </Tag>
                    )
                  },
                  {
                    title: "Granted",
                    dataIndex: "created_at",
                    render: (v: string) => (
                      <span className="text-[11px] text-slate-400 font-mono">
                        {v ? new Date(v).toLocaleDateString() : "—"}
                      </span>
                    )
                  },
                  {
                    title: "Revoke",
                    key: "revoke",
                    render: (_: any, r: DocumentPermission) => (
                      <Button
                        size="small"
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleRevokeShare(r.id)}
                      />
                    )
                  }
                ]}
              />
            </div>
          </div>
        )}
      </Modal>

      {/* Generate Report Modal */}
      <Modal
        title={
          <Space>
            <RobotOutlined className="text-blue-400" />
            <span>Generate Grounded Intelligence Report</span>
          </Space>
        }
        open={isGenerateModalOpen}
        onCancel={() => setIsGenerateModalOpen(false)}
        onOk={handleGenerateSubmit}
        confirmLoading={generating}
        okText="Generate Document"
        okButtonProps={{ className: "bg-blue-600 font-semibold" }}
      >
        <div className="space-y-4 py-3">
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Report Title *
            </label>
            <Input
              placeholder="e.g. Mangalore Refinery Pressure Analysis Report"
              value={reportTitle}
              onChange={(e) => setReportTitle(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Analysis Context / Specific Instructions (Optional)
            </label>
            <Input.TextArea
              rows={3}
              placeholder="e.g. Focus on safety protocols and emergency shutdown steps..."
              value={reportTopic}
              onChange={(e) => setReportTopic(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Target Source Document
            </label>
            <Select
              value={selectedDocForReport || "ALL"}
              onChange={(v) => setSelectedDocForReport(v === "ALL" ? null : v)}
              className="w-full"
              options={[
                { label: "All Accessible Documents", value: "ALL" },
                ...p.documents.map((d) => ({
                  label: `${d.filename} (${d.owner_department_name || "General"})`,
                  value: d.id
                }))
              ]}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">
              Output Format
            </label>
            <Radio.Group value={reportFormat} onChange={(e) => setReportFormat(e.target.value)}>
              <Radio value="pdf">PDF Document (.pdf)</Radio>
              <Radio value="docx">Word Document (.docx)</Radio>
            </Radio.Group>
          </div>
        </div>
      </Modal>
    </div>
  );
}
