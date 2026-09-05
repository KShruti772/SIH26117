"use client";

import React, { useState, useEffect } from "react";
import {
  Alert,
  App,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  ReloadOutlined
} from "@ant-design/icons";
import {
  sandboxApi,
  SandboxExecutionResponse,
  SandboxFileRecord,
  SandboxExecutionRecord
} from "../../lib/api/sandbox";

export interface SandboxHistoryItem {
  id: string;
  code: string;
  language: string;
  timestamp: string;
  response: SandboxExecutionResponse | null;
  error?: string | null;
}

interface SandboxViewProps {
  code: string;
  setCode: (code: string) => void;
  executing: boolean;
  response: SandboxExecutionResponse | null;
  error: string | null;
  onExecute: () => void;
  history?: SandboxHistoryItem[];
  onSelectHistory?: (item: SandboxHistoryItem) => void;
  onClearHistory?: () => void;
}

const PRESET_SCRIPTS: { label: string; code: string }[] = [
  {
    label: "Basic Arithmetic & Variables",
    code: `x = 10\ny = 20\nprint(f"Result: {x + y}")`
  },
  {
    label: "Factorial Function",
    code: `def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n\nfor num in range(1, 8):\n    print(f"{num}! = {factorial(num)}")`
  },
  {
    label: "Binary Search Algorithm",
    code: `def binary_search(arr, target):\n    low, high = 0, len(arr) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1\n\ndata = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]\ntarget = 23\nresult = binary_search(data, target)\nprint(f"Searching for {target} in: {data}")\nprint(f"Found {target} at index: {result}")`
  },
  {
    label: "Data Analysis / Statistics",
    code: `values = [42.5, 48.0, 52.3, 61.8, 58.2, 49.6, 65.1]\n\nn = len(values)\nmean = sum(values) / n\nvariance = sum((x - mean) ** 2 for x in values) / (n - 1)\nstd_dev = variance ** 0.5\n\nprint(f"Sample Count: {n}")\nprint(f"Mean: {mean:.2f}")\nprint(f"Std Dev: {std_dev:.2f}")`
  }
];

export default function SandboxView({
  code,
  setCode,
  executing,
  response,
  error,
  onExecute,
  history = [],
  onSelectHistory,
  onClearHistory
}: SandboxViewProps) {
  const { message } = App.useApp();
  const [activeTab, setActiveTab] = useState<string>("editor");
  const [workspaceFiles, setWorkspaceFiles] = useState<SandboxFileRecord[]>([]);
  const [loadingFiles, setLoadingFiles] = useState<boolean>(false);
  const [dbExecutions, setDbExecutions] = useState<SandboxExecutionRecord[]>([]);
  const [loadingExecutions, setLoadingExecutions] = useState<boolean>(false);
  const [previewFile, setPreviewFile] = useState<SandboxFileRecord | null>(null);
  const [previewExecution, setPreviewExecution] = useState<SandboxExecutionRecord | null>(null);

  const fetchWorkspaceFiles = async () => {
    setLoadingFiles(true);
    try {
      const files = await sandboxApi.getFiles();
      setWorkspaceFiles(files || []);
    } catch (err: any) {
      console.warn("Could not fetch sandbox files:", err);
    } finally {
      setLoadingFiles(false);
    }
  };

  const fetchDbExecutions = async () => {
    setLoadingExecutions(true);
    try {
      const execs = await sandboxApi.getExecutions(50);
      setDbExecutions(execs || []);
    } catch (err: any) {
      console.warn("Could not fetch sandbox executions:", err);
    } finally {
      setLoadingExecutions(false);
    }
  };

  useEffect(() => {
    if (activeTab === "files") {
      fetchWorkspaceFiles();
    } else if (activeTab === "history") {
      fetchDbExecutions();
    }
  }, [activeTab]);

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    message.success(`${label} copied to clipboard`);
  };

  const handleSelectPreset = (value: string) => {
    const preset = PRESET_SCRIPTS.find((p) => p.label === value);
    if (preset) {
      setCode(preset.code);
    }
  };

  const handleLoadFileToEditor = async (file: SandboxFileRecord) => {
    try {
      const details = await sandboxApi.getFile(file.id);
      if (details && details.content) {
        setCode(details.content);
        setActiveTab("editor");
        message.success(`Loaded '${file.filename}' into code editor.`);
      } else {
        message.warning("Could not read file content.");
      }
    } catch (e: any) {
      message.error(`Error loading file: ${e.message || e}`);
    }
  };

  const handleLoadExecutionCode = (rec: SandboxExecutionRecord) => {
    if (rec.code) {
      setCode(rec.code);
      setActiveTab("editor");
      message.success(`Loaded script from execution into editor.`);
    } else {
      message.info("No source code recorded for this execution.");
    }
  };

  return (
    <div className="aegis-view-stack space-y-6">
      {/* Top Header */}
      <section className="aegis-view-heading flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <Typography.Title level={2} className="!mb-1">
            Isolated Code Sandbox
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Execute Python scripts in an isolated, resource-constrained subprocess environment with strict RBAC isolation.
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Tag color="cyan">SUBPROCESS ISOLATION</Tag>
          <Tag color="blue">LOCAL CPU ONLY</Tag>
          <Tag color="success">ZERO CLOUD CALLS</Tag>
        </Space>
      </section>

      {/* Tabs Control */}
      <div className="border-b border-slate-800">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: "editor",
              label: (
                <Space>
                  <CodeOutlined />
                  <span>Editor & Run</span>
                </Space>
              )
            },
            {
              key: "files",
              label: (
                <Space>
                  <FileTextOutlined />
                  <span>Workspace Files</span>
                  {workspaceFiles.length > 0 && (
                    <Badge count={workspaceFiles.length} style={{ backgroundColor: "#2563eb" }} />
                  )}
                </Space>
              )
            },
            {
              key: "history",
              label: (
                <Space>
                  <HistoryOutlined />
                  <span>Execution Records</span>
                  {dbExecutions.length > 0 && (
                    <Badge count={dbExecutions.length} style={{ backgroundColor: "#1e293b" }} />
                  )}
                </Space>
              )
            }
          ]}
        />
      </div>

      {/* TAB 1: EDITOR & RUN */}
      {activeTab === "editor" && (
        <Row gutter={[20, 20]} className="items-stretch">
          {/* LEFT COLUMN: CODE EDITOR */}
          <Col xs={24} lg={12} className="flex flex-col">
            <Card
              className="aegis-panel-card flex-1 flex flex-col"
              styles={{ body: { display: "flex", flexDirection: "column", flex: 1, padding: "16px" } }}
              title={
                <Space>
                  <CodeOutlined />
                  <span className="font-bold uppercase tracking-wider text-xs">PYTHON 3 SCRIPT</span>
                </Space>
              }
              extra={
                <div className="flex items-center space-x-2">
                  <Select
                    placeholder="Load template script…"
                    size="small"
                    style={{ width: 190 }}
                    onChange={handleSelectPreset}
                    options={PRESET_SCRIPTS.map((p) => ({ label: p.label, value: p.label }))}
                  />
                  <Button
                    type="text"
                    size="small"
                    onClick={() => setCode("")}
                    className="text-slate-400 hover:text-slate-200 text-xs"
                  >
                    Clear
                  </Button>
                </div>
              }
            >
              {/* Editor Textarea */}
              <div className="flex-1 flex flex-col bg-[#050811] rounded-xl border border-slate-800/80 overflow-hidden mb-4">
                <div className="flex items-center justify-between px-4 py-2 bg-[#090e1a] border-b border-slate-800/80 text-xs text-slate-400 font-mono">
                  <Space size="small">
                    <Badge status="processing" color="#3b82f6" />
                    <span className="text-slate-300 font-bold">script.py</span>
                  </Space>
                  <span>{code.split("\n").length} lines · {code.length} chars</span>
                </div>
                <textarea
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  disabled={executing}
                  placeholder="# Write Python code to execute in the secure sandbox...&#10;print('Hello Aegis!')"
                  className="flex-1 w-full p-4 bg-transparent text-slate-100 placeholder-slate-600 font-mono text-[13px] leading-relaxed resize-none focus:outline-none border-none min-h-[320px]"
                  rows={16}
                  spellCheck={false}
                />
              </div>

              {/* Run Code Action Bar */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                <span className="text-xs text-slate-400">
                  Environment: <span className="font-mono text-slate-200">Python 3.12 (Local)</span>
                </span>
                <Button
                  type="primary"
                  size="large"
                  icon={<PlayCircleOutlined />}
                  loading={executing}
                  disabled={executing || !code.trim()}
                  onClick={onExecute}
                  className="px-6 font-bold shadow-lg shadow-blue-500/10"
                >
                  Run Code
                </Button>
              </div>
            </Card>
          </Col>

          {/* RIGHT COLUMN: EXECUTION RESULT */}
          <Col xs={24} lg={12} className="flex flex-col">
            <Card
              className="aegis-panel-card flex-1 flex flex-col"
              styles={{ body: { display: "flex", flexDirection: "column", flex: 1, padding: "16px" } }}
              title={
                <Space>
                  <ClockCircleOutlined />
                  <span className="font-bold uppercase tracking-wider text-xs">EXECUTION RESULT</span>
                </Space>
              }
              extra={
                response && (
                  <Tag color={response.success ? "success" : "error"} className="!mr-0 font-mono font-bold">
                    {response.success ? "✓ SUCCESS" : "✕ FAILED"}
                  </Tag>
                )
              }
            >
              {/* Top Metadata Metrics Section */}
              <div className="grid grid-cols-3 gap-3 p-3.5 bg-[#080d1a] border border-slate-800/80 rounded-xl mb-4 text-xs font-mono">
                <div>
                  <span className="text-slate-400 block text-[11px] font-sans">Status</span>
                  <span className={`text-sm font-bold ${response ? (response.success ? "text-emerald-400" : "text-rose-400") : "text-slate-500"}`}>
                    {response ? (response.success ? "SUCCESS" : "FAILED") : error ? "ERROR" : "IDLE"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px] font-sans">Execution time</span>
                  <span className="text-sm font-bold text-slate-200">
                    {response?.duration_ms != null ? `${response.duration_ms} ms` : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px] font-sans">Exit code</span>
                  <span className={`text-sm font-bold ${response ? (response.exit_code === 0 ? "text-emerald-400" : "text-rose-400") : "text-slate-500"}`}>
                    {response?.exit_code != null ? response.exit_code : "—"}
                  </span>
                </div>
              </div>

              {/* Error Banner */}
              {error && (
                <Alert
                  type="error"
                  showIcon
                  title="Execution Error"
                  description={
                    <div>
                      <p className="mb-1">{error}</p>
                      <Typography.Text type="secondary" className="text-xs font-mono">
                        Host: http://127.0.0.1:8000
                      </Typography.Text>
                    </div>
                  }
                  className="mb-4"
                />
              )}

              {/* Output Stream Areas */}
              {executing ? (
                <div className="flex-1 flex flex-col items-center justify-center p-12 bg-[#050811] rounded-xl border border-slate-800 text-slate-400 space-y-3 min-h-[300px]">
                  <ReloadOutlined spin className="text-2xl text-blue-400" />
                  <span className="text-xs font-mono uppercase tracking-wider text-slate-300">
                    Executing in isolated subprocess...
                  </span>
                  <span className="text-[11px] text-slate-500">
                    Enforcing timeouts, output size limits, and system protection...
                  </span>
                </div>
              ) : !response && !error ? (
                <div className="flex-1 flex flex-col items-center justify-center p-12 bg-[#050811] rounded-xl border border-dashed border-slate-800 text-center min-h-[300px]">
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="Click 'Run Code' to execute Python code and view execution output."
                  />
                </div>
              ) : (
                <div className="flex-1 flex flex-col gap-4 overflow-y-auto max-h-[560px] min-h-[280px] pr-1">
                  {/* OUTPUT Section (STDOUT) */}
                  <div className="flex flex-col flex-1 space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-bold text-slate-300 uppercase tracking-wider text-[11px]">
                        OUTPUT (STDOUT)
                      </span>
                      {response?.stdout && (
                        <Tooltip title="Copy Output">
                          <Button
                            type="text"
                            size="small"
                            icon={<CopyOutlined />}
                            onClick={() => handleCopy(response.stdout, "OUTPUT")}
                            className="text-slate-400 hover:text-slate-200 text-xs"
                          >
                            Copy
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                    <pre className="flex-1 p-4 bg-[#050811] border border-slate-800/80 rounded-xl text-emerald-400 font-mono text-sm leading-relaxed overflow-auto whitespace-pre-wrap break-words min-h-[140px] max-h-[260px]">
                      {response?.stdout ? response.stdout : <span className="text-slate-600 italic">None</span>}
                    </pre>
                  </div>

                  {/* ERROR Section (STDERR) */}
                  <div className="flex flex-col space-y-1.5">
                    <div className="flex justify-between items-center text-xs">
                      <span className={`font-bold uppercase tracking-wider text-[11px] ${response?.stderr ? "text-rose-400" : "text-slate-400"}`}>
                        ERROR (STDERR)
                      </span>
                      {response?.stderr && (
                        <Tooltip title="Copy Error">
                          <Button
                            type="text"
                            size="small"
                            icon={<CopyOutlined />}
                            onClick={() => handleCopy(response.stderr, "ERROR")}
                            className="text-slate-400 hover:text-slate-200 text-xs"
                          >
                            Copy
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                    <pre className={`p-4 rounded-xl border font-mono text-sm leading-relaxed overflow-auto whitespace-pre-wrap break-words min-h-[80px] max-h-[180px] ${
                      response?.stderr
                        ? "bg-[#160b0e] border-rose-900/40 text-rose-300"
                        : "bg-[#050811] border-slate-800/80 text-slate-500"
                    }`}>
                      {response?.stderr ? response.stderr : <span className="text-slate-600 italic">None</span>}
                    </pre>
                  </div>
                </div>
              )}
            </Card>
          </Col>
        </Row>
      )}

      {/* TAB 2: WORKSPACE FILES */}
      {activeTab === "files" && (
        <Card
          className="aegis-panel-card"
          title={
            <Space>
              <FileTextOutlined />
              <span className="font-bold uppercase tracking-wider text-xs">Workspace Scripts & Files</span>
            </Space>
          }
          extra={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={loadingFiles}
              onClick={fetchWorkspaceFiles}
            >
              Refresh
            </Button>
          }
        >
          <Table
            dataSource={workspaceFiles}
            rowKey="id"
            loading={loadingFiles}
            pagination={{ pageSize: 10 }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="No files in sandbox."
                />
              )
            }}
            columns={[
              {
                title: "Filename",
                dataIndex: "filename",
                key: "filename",
                render: (name: string) => (
                  <Space>
                    <CodeOutlined className="text-blue-400" />
                    <span className="font-mono font-bold text-slate-200">{name}</span>
                  </Space>
                )
              },
              {
                title: "Lines",
                dataIndex: "lines_count",
                key: "lines_count",
                width: 90,
                render: (lines: number) => <span className="font-mono text-xs">{lines || "—"}</span>
              },
              {
                title: "Size",
                dataIndex: "file_size",
                key: "file_size",
                width: 100,
                render: (bytes: number) => (
                  <span className="font-mono text-xs text-slate-400">
                    {bytes ? `${bytes} B` : "0 B"}
                  </span>
                )
              },
              {
                title: "SHA-256",
                dataIndex: "sha256_hash",
                key: "sha256_hash",
                render: (hash: string) => (
                  <span className="font-mono text-xs text-slate-500 truncate block max-w-[140px]">
                    {hash ? `${hash.slice(0, 12)}...` : "—"}
                  </span>
                )
              },
              {
                title: "Created",
                dataIndex: "created_at",
                key: "created_at",
                render: (dt: string) => (
                  <span className="text-xs text-slate-400">
                    {dt ? new Date(dt).toLocaleString() : "—"}
                  </span>
                )
              },
              {
                title: "Actions",
                key: "actions",
                align: "right",
                render: (_: any, record: SandboxFileRecord) => (
                  <Space size="small">
                    <Tooltip title="View Source">
                      <Button
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={async () => {
                          const det = await sandboxApi.getFile(record.id);
                          setPreviewFile(det);
                        }}
                      />
                    </Tooltip>
                    <Tooltip title="Load in Editor">
                      <Button
                        size="small"
                        type="primary"
                        ghost
                        icon={<PlayCircleOutlined />}
                        onClick={() => handleLoadFileToEditor(record)}
                      >
                        Edit & Run
                      </Button>
                    </Tooltip>
                    <Tooltip title="Download File">
                      <a
                        href={`http://127.0.0.1:8000/sandbox/artifacts/${record.id}/download`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <Button size="small" icon={<DownloadOutlined />} />
                      </a>
                    </Tooltip>
                  </Space>
                )
              }
            ]}
          />
        </Card>
      )}

      {/* TAB 3: EXECUTION RECORDS */}
      {activeTab === "history" && (
        <Card
          className="aegis-panel-card"
          title={
            <Space>
              <HistoryOutlined />
              <span className="font-bold uppercase tracking-wider text-xs">Real Execution Telemetry Records</span>
            </Space>
          }
          extra={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={loadingExecutions}
              onClick={fetchDbExecutions}
            >
              Refresh
            </Button>
          }
        >
          <Table
            dataSource={dbExecutions}
            rowKey="id"
            loading={loadingExecutions}
            pagination={{ pageSize: 10 }}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="No sandbox executions recorded yet. Execute code to view persistent audit records."
                />
              )
            }}
            columns={[
              {
                title: "Status",
                key: "status",
                width: 110,
                render: (_: any, rec: SandboxExecutionRecord) => {
                  const success = rec.exit_code === 0 && !rec.timed_out;
                  return (
                    <Tag color={success ? "success" : "error"} className="font-mono font-bold text-xs">
                      {success ? "✓ PASS" : "✕ FAIL"}
                    </Tag>
                  );
                }
              },
              {
                title: "Script",
                dataIndex: "script_filename",
                key: "script_filename",
                render: (s: string) => (
                  <span className="font-mono font-bold text-slate-200 text-xs">{s || "script.py"}</span>
                )
              },
              {
                title: "Exit Code",
                dataIndex: "exit_code",
                key: "exit_code",
                width: 90,
                render: (code: number) => <span className="font-mono text-xs">{code}</span>
              },
              {
                title: "Duration",
                dataIndex: "duration_ms",
                key: "duration_ms",
                width: 100,
                render: (ms: number) => <span className="font-mono text-xs text-slate-300">{ms || 0} ms</span>
              },
              {
                title: "STDOUT Snippet",
                dataIndex: "stdout",
                key: "stdout",
                render: (out: string) => (
                  <span className="font-mono text-xs text-emerald-400 truncate block max-w-[200px]">
                    {out ? out.trim().replace(/\n/g, " ") : "—"}
                  </span>
                )
              },
              {
                title: "Executed At",
                dataIndex: "created_at",
                key: "created_at",
                render: (dt: string) => (
                  <span className="text-xs text-slate-400">
                    {dt ? new Date(dt).toLocaleString() : "—"}
                  </span>
                )
              },
              {
                title: "Actions",
                key: "actions",
                align: "right",
                render: (_: any, record: SandboxExecutionRecord) => (
                  <Space size="small">
                    <Tooltip title="View Telemetry Details">
                      <Button
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => setPreviewExecution(record)}
                      />
                    </Tooltip>
                    {record.code && (
                      <Tooltip title="Load Code in Editor">
                        <Button
                          size="small"
                          type="primary"
                          ghost
                          icon={<CodeOutlined />}
                          onClick={() => handleLoadExecutionCode(record)}
                        >
                          Load Code
                        </Button>
                      </Tooltip>
                    )}
                  </Space>
                )
              }
            ]}
          />
        </Card>
      )}

      {/* File Source Modal */}
      <Modal
        title={
          <Space>
            <CodeOutlined className="text-blue-400" />
            <span>{previewFile?.filename || "File Preview"}</span>
          </Space>
        }
        open={Boolean(previewFile)}
        onCancel={() => setPreviewFile(null)}
        footer={[
          <Button key="close" onClick={() => setPreviewFile(null)}>
            Close
          </Button>,
          previewFile && (
            <Button
              key="load"
              type="primary"
              onClick={() => {
                if (previewFile?.content) {
                  setCode(previewFile.content);
                  setPreviewFile(null);
                  setActiveTab("editor");
                  message.success(`Loaded '${previewFile.filename}' into code editor.`);
                }
              }}
            >
              Load in Editor
            </Button>
          )
        ]}
        width={700}
      >
        <div className="space-y-3 font-mono text-xs">
          <div className="flex justify-between text-slate-400 border-b border-slate-800 pb-2">
            <span>{previewFile?.lines_count || 0} lines · {previewFile?.file_size || 0} bytes</span>
            <span>SHA-256: {previewFile?.sha256_hash?.slice(0, 16)}...</span>
          </div>
          <pre className="p-4 bg-[#050811] border border-slate-800 rounded-xl text-slate-100 font-mono text-xs overflow-auto max-h-[400px] whitespace-pre">
            {previewFile?.content || "# File is empty."}
          </pre>
        </div>
      </Modal>

      {/* Execution Telemetry Modal */}
      <Modal
        title={
          <Space>
            <HistoryOutlined className="text-blue-400" />
            <span>Execution Telemetry ({previewExecution?.script_filename || "script.py"})</span>
          </Space>
        }
        open={Boolean(previewExecution)}
        onCancel={() => setPreviewExecution(null)}
        footer={[
          <Button key="close" onClick={() => setPreviewExecution(null)}>
            Close
          </Button>,
          previewExecution?.code && (
            <Button
              key="load"
              type="primary"
              onClick={() => {
                if (previewExecution?.code) {
                  setCode(previewExecution.code);
                  setPreviewExecution(null);
                  setActiveTab("editor");
                  message.success("Loaded script into code editor.");
                }
              }}
            >
              Load Code in Editor
            </Button>
          )
        ]}
        width={750}
      >
        <div className="space-y-4 font-mono text-xs">
          <div className="grid grid-cols-3 gap-2 p-3 bg-[#080d1a] rounded-lg border border-slate-800">
            <div>
              <span className="text-slate-500 block text-[10px]">Exit Code</span>
              <span className="font-bold text-slate-200">{previewExecution?.exit_code}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Duration</span>
              <span className="font-bold text-slate-200">{previewExecution?.duration_ms} ms</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Timed Out</span>
              <span className="font-bold text-slate-200">{previewExecution?.timed_out ? "YES" : "NO"}</span>
            </div>
          </div>

          {previewExecution?.code && (
            <div>
              <span className="text-slate-400 font-bold uppercase block mb-1">Source Code:</span>
              <pre className="p-3 bg-[#050811] border border-slate-800 rounded-lg text-emerald-300 overflow-auto max-h-[180px] whitespace-pre">
                {previewExecution.code}
              </pre>
            </div>
          )}

          <div>
            <span className="text-slate-400 font-bold uppercase block mb-1">STDOUT:</span>
            <pre className="p-3 bg-[#050811] border border-slate-800 rounded-lg text-slate-100 overflow-auto max-h-[140px] whitespace-pre">
              {previewExecution?.stdout || "<empty>"}
            </pre>
          </div>

          {previewExecution?.stderr && (
            <div>
              <span className="text-rose-400 font-bold uppercase block mb-1">STDERR:</span>
              <pre className="p-3 bg-[#180808] border border-rose-900/50 rounded-lg text-rose-300 overflow-auto max-h-[140px] whitespace-pre">
                {previewExecution.stderr}
              </pre>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
