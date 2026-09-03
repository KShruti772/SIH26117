"use client";

import React, { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  message as antMessage
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  ReloadOutlined
} from "@ant-design/icons";
import type { SandboxExecutionResponse } from "../../lib/api/sandbox";

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
    code: `x = 10
y = 20
print(f"Result: {x + y}")`
  },
  {
    label: "Factorial Function",
    code: `def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

for num in range(1, 8):
    print(f"{num}! = {factorial(num)}")`
  },
  {
    label: "Binary Search Algorithm",
    code: `def binary_search(arr, target):
    low, high = 0, len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1

data = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]
target = 23
result = binary_search(data, target)
print(f"Searching for {target} in: {data}")
print(f"Found {target} at index: {result}")`
  },
  {
    label: "Data Analysis / Statistics",
    code: `values = [42.5, 48.0, 52.3, 61.8, 58.2, 49.6, 65.1]

n = len(values)
mean = sum(values) / n
variance = sum((x - mean) ** 2 for x in values) / (n - 1)
std_dev = variance ** 0.5

print(f"Sample Count: {n}")
print(f"Mean: {mean:.2f}")
print(f"Std Dev: {std_dev:.2f}")`
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
  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    antMessage.success(`${label} copied to clipboard`);
  };

  const handleSelectPreset = (value: string) => {
    const preset = PRESET_SCRIPTS.find((p) => p.label === value);
    if (preset) {
      setCode(preset.code);
    }
  };

  return (
    <div className="aegis-view-stack space-y-6">
      {/* Top Header */}
      <section className="aegis-view-heading">
        <div>
          <Typography.Title level={2} className="!mb-1">
            Isolated Code Sandbox
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Execute Python scripts in an isolated, resource-constrained subprocess environment.
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Tag color="cyan">SUBPROCESS ISOLATION</Tag>
          <Tag color="blue">LOCAL CPU ONLY</Tag>
          <Tag color="success">ZERO CLOUD CALLS</Tag>
        </Space>
      </section>

      {/* Main 2-Column Grid */}
      <Row gutter={[20, 20]} className="items-stretch">
        {/* LEFT COLUMN: CODE EDITOR */}
        <Col xs={24} lg={12} className="flex flex-col">
          <Card
            className="aegis-panel-card flex-1 flex flex-col"
            styles={{ body: { display: "flex", flexDirection: "column", flex: 1, padding: "16px" } }}
            title={
              <Space>
                <CodeOutlined />
                <span className="font-bold uppercase tracking-wider text-xs">CODE</span>
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
                      OUTPUT
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
                      ERROR
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

      {/* Execution History Section */}
      {history.length > 0 && (
        <Card
          className="aegis-panel-card"
          title={
            <Space>
              <HistoryOutlined />
              <span className="font-bold uppercase tracking-wider text-xs">Recent Executions</span>
              <Badge count={history.length} style={{ backgroundColor: "#1e293b" }} />
            </Space>
          }
          extra={
            onClearHistory && (
              <Button size="small" danger icon={<DeleteOutlined />} onClick={onClearHistory}>
                Clear History
              </Button>
            )
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {history.map((item) => (
              <div
                key={item.id}
                onClick={() => onSelectHistory && onSelectHistory(item)}
                className="p-3.5 bg-[#080d1a] hover:bg-[#0f172a] border border-slate-800 hover:border-blue-500/40 rounded-xl cursor-pointer transition-all space-y-2"
              >
                <div className="flex justify-between items-center text-xs">
                  <Space size="small">
                    {item.response?.success ? (
                      <CheckCircleOutlined className="text-emerald-400" />
                    ) : (
                      <CloseCircleOutlined className="text-rose-400" />
                    )}
                    <span className="font-mono text-slate-300">
                      {new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </Space>
                  <Tag color={item.response?.success ? "success" : "error"} className="!mr-0 text-[10px] font-mono font-bold">
                    {item.response?.duration_ms != null ? `${item.response.duration_ms}ms` : "ERR"}
                  </Tag>
                </div>
                <div className="text-xs font-mono text-slate-400 line-clamp-2 bg-[#050811] p-2 rounded-lg border border-slate-900">
                  {item.code}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
