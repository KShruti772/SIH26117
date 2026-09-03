"use client";

import React, { useState, useEffect } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message as antMessage
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
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  TableOutlined,
  UploadOutlined
} from "@ant-design/icons";
import { ragApi, DocumentInfo, GeneratedDocument } from "../../lib/api/rag";
import { getToken } from "../../lib/security/token";

const { Dragger } = Upload;

interface Props {
  documents: DocumentInfo[];
  loading: boolean;
  error: string | null;
  file: File | null;
  uploading: boolean;
  uploadSuccess: string | null;
  uploadError: string | null;
  search: string;
  setSearch: (v: string) => void;
  status: string;
  setStatus: (v: string) => void;
  type: string;
  setType: (v: string) => void;
  onFile: (f: File) => void;
  onUpload: () => void;
  onRefresh: () => void;
  onReindex: (id: string) => void;
  onDelete: (id: string, name: string) => void;
  reindexing: string | null;
  deleting: string | null;
}

export default function DocumentsView(p: Props) {
  const [activeTab, setActiveTab] = useState<string>("source");
  const [generatedDocs, setGeneratedDocs] = useState<GeneratedDocument[]>([]);
  const [genLoading, setGenLoading] = useState<boolean>(false);
  const [genError, setGenError] = useState<string | null>(null);

  // Generate Report Modal States
  const [isGenerateModalOpen, setIsGenerateModalOpen] = useState(false);
  const [reportTitle, setReportTitle] = useState("");
  const [reportTopic, setReportTopic] = useState("");
  const [reportFormat, setReportFormat] = useState<string>("pdf");
  const [selectedDocForReport, setSelectedDocForReport] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

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

  useEffect(() => {
    loadGeneratedDocuments();
  }, []);

  const handleDownload = async (doc: GeneratedDocument) => {
    try {
      const token = getToken();
      const res = await fetch(`http://127.0.0.1:8000/documents/generated/${doc.id}/download`, {
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
      antMessage.error(e.message || "Failed to download document.");
    }
  };

  const handleDeleteGenerated = async (id: string) => {
    try {
      await ragApi.deleteGeneratedDocument(id);
      antMessage.success("Report deleted.");
      loadGeneratedDocuments();
    } catch (e: any) {
      antMessage.error(e.message || "Failed to delete report.");
    }
  };

  const handleGenerateSubmit = async () => {
    if (!reportTitle.trim()) {
      antMessage.warning("Please enter a report title.");
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
      antMessage.success(`Report '${reportTitle}' generated successfully!`);
      setIsGenerateModalOpen(false);
      setReportTitle("");
      setReportTopic("");
      loadGeneratedDocuments();
      setActiveTab("generated");
    } catch (err: any) {
      antMessage.error(err.message || "Failed generating report.");
    } finally {
      setGenerating(false);
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

  const sourceColumns = [
    {
      title: "Filename",
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
      title: "Category",
      dataIndex: "category",
      render: (v: string, d: DocumentInfo) => {
        const cat = v || (d.filename.split(".").pop() || "doc").toUpperCase();
        let color = "blue";
        if (cat === "spreadsheet" || ["XLSX", "CSV"].includes(cat)) color = "green";
        if (cat === "presentation" || ["PPTX"].includes(cat)) color = "gold";
        if (cat === "image" || ["PNG", "JPG"].includes(cat)) color = "purple";
        if (cat === "code" || ["PY", "SQL", "JS"].includes(cat)) color = "cyan";
        return (
          <Tag color={color} className="font-mono text-[10px] font-bold uppercase">
            {cat}
          </Tag>
        );
      }
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
            {v ? v.toUpperCase() : "INDEXED"}
          </Tag>
        );
      }
    },
    {
      title: "Extraction",
      dataIndex: "extraction_method",
      render: (v: string) => (
        <span className="font-mono text-xs text-slate-300">
          {v ? v.replace("_", " ") : "native"}
        </span>
      )
    },
    {
      title: "Chunks",
      dataIndex: "chunk_count",
      render: (v: any, d: DocumentInfo) => (
        <Tag color="cyan" className="font-mono text-xs">
          {d.chunk_count ?? d.chunks ?? "—"} chunks
        </Tag>
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: any, d: DocumentInfo) => (
        <Space size="small">
          <Tooltip title="Delete Document">
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              loading={p.deleting === d.id}
              onClick={() => p.onDelete(d.id, d.filename)}
            />
          </Tooltip>
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
      title: "Status",
      dataIndex: "status",
      render: (v: string) => (
        <Tag color="success" className="font-mono text-[10px] font-bold uppercase">
          {v || "COMPLETED"}
        </Tag>
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
            onClick={() => handleDownload(d)}
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
            <span>Document & Intelligence Repository</span>
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Manage authoritative source documents and generate formal intelligence reports.
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
              title={<span className="text-slate-400 text-xs uppercase font-bold">Source Documents</span>}
              value={p.documents.length}
              styles={{ content: { color: "#38bdf8", fontWeight: 700 } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card className="aegis-panel-card bg-[#080d1a] border-slate-800">
            <Statistic
              title={<span className="text-slate-400 text-xs uppercase font-bold">Total Chunks</span>}
              value={p.documents.reduce((acc, d) => acc + (d.chunk_count || d.chunks || 0), 0)}
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
              title={<span className="text-slate-400 text-xs uppercase font-bold">Sovereign Mode</span>}
              value="100% Local"
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
                  {/* Upload Card */}
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
                          Click or drag any supported file to upload
                        </p>
                        <p className="text-slate-400 text-xs">
                          PDF, Word, Excel, CSV, PowerPoint, Images, Code, Text
                        </p>
                        <p className="text-slate-500 text-[11px] mt-1">
                          100% On-Premise · Magic-Byte Validated · No Cloud Egress
                        </p>
                      </Dragger>

                      {p.file && (
                        <div className="mt-4 p-3 bg-[#080d1a] border border-slate-800 rounded-lg flex items-center justify-between">
                          <div className="truncate pr-2 text-xs text-slate-200 font-semibold">
                            {p.file.name}
                          </div>
                          <Button
                            type="primary"
                            size="small"
                            loading={p.uploading}
                            onClick={p.onUpload}
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
                      scroll={{ x: 700 }}
                      pagination={{ pageSize: 6 }}
                      locale={{
                        emptyText: (
                          <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description="No documents available in knowledge base."
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
                { label: "All Indexed Documents", value: "ALL" },
                ...p.documents.map((d) => ({
                  label: d.filename,
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
