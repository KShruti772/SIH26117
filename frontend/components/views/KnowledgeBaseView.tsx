"use client";

import React, { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  message as antMessage
} from "antd";
import {
  BookOutlined,
  CheckCircleOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileTextOutlined,
  FileWordOutlined,
  FilterOutlined,
  HistoryOutlined,
  PictureOutlined,
  ReloadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  ThunderboltOutlined
} from "@ant-design/icons";
import {
  ragApi,
  DocumentInfo,
  RagQueryResponse,
  GroundedAnswerResponse,
  GroundedSource,
  GeneratedDocument,
  KnowledgeBaseGenerationResult
} from "../../lib/api/rag";
import { getToken } from "../../lib/security/token";
import type { KnowledgeHistoryItem } from "./HistoryView";

interface KnowledgeBaseViewProps {
  documents: DocumentInfo[];
  loading: boolean;
  error: string | null;
  query: string;
  setQuery: (v: string) => void;
  topK: number;
  setTopK: (v: number) => void;
  selectedDocId?: string | null;
  setSelectedDocId?: (id: string | null) => void;
  onSearch: () => void;
  searching: boolean;
  result: GroundedAnswerResponse | RagQueryResponse | KnowledgeBaseGenerationResult | null;
  queryError: string | null;
  history?: KnowledgeHistoryItem[];
  onSelectHistory?: (item: KnowledgeHistoryItem) => void;
  onRefreshDocuments?: () => void;
}

export default function KnowledgeBaseView(p: KnowledgeBaseViewProps) {
  const [activeEvidenceKeys, setActiveEvidenceKeys] = useState<string[]>([]);
  const [exportingReport, setExportingReport] = useState(false);

  const handleCopyText = (text: string) => {
    navigator.clipboard.writeText(text);
    antMessage.success("Text copied to clipboard");
  };

  const handleDownloadGenerated = async (doc: GeneratedDocument) => {
    try {
      const token = getToken();
      const res = await fetch(`http://127.0.0.1:8000/documents/generated/${doc.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      antMessage.success(`Downloaded ${doc.filename}`);
    } catch (err: any) {
      antMessage.error(err.message || "Failed downloading generated document.");
    }
  };

  // Extract answer text, sources, evidence chunks, or generated report
  const parsedData = React.useMemo(() => {
    if (!p.result) return null;

    const res = p.result;

    // Check if result is a Generated Report result
    const isGenResult = Boolean(res && "isGenerationResult" in res && (res as KnowledgeBaseGenerationResult).isGenerationResult);
    if (isGenResult) {
      const genObj = res as KnowledgeBaseGenerationResult;
      return {
        isGenerationResult: true,
        generatedDocument: genObj.generatedDocument,
        sourceFilename: genObj.sourceFilename,
        query: genObj.query || p.query,
        answer: null,
        isGrounded: true,
        sources: [],
        chunks: []
      };
    }

    const isGroundedResp = Boolean(res && "answer" in res && typeof (res as GroundedAnswerResponse).answer === "string");
    const groundedObj = isGroundedResp ? (res as GroundedAnswerResponse) : null;
    const answer = groundedObj ? groundedObj.answer : null;
    const isGrounded = groundedObj ? groundedObj.grounded : true;
    const sources: GroundedSource[] = groundedObj && groundedObj.sources ? groundedObj.sources : [];
    const chunks = (res as any).results || [];

    // If sources list is empty from grounded response, fallback to extracting from chunks
    let finalSources: GroundedSource[] = sources;
    if (finalSources.length === 0 && chunks.length > 0) {
      const docMap = new Map<string, { document_id: string; filename: string; pages: Set<number>; relevance: string }>();
      chunks.forEach((r: any) => {
        const dId = r.metadata?.document_id || "doc";
        const docName = r.metadata?.filename || r.metadata?.document_name || "Document";
        const page = r.metadata?.page_number ?? 1;
        if (!docMap.has(dId)) {
          docMap.set(dId, {
            document_id: dId,
            filename: docName,
            pages: new Set<number>(),
            relevance: r.relevance || "High"
          });
        }
        docMap.get(dId)!.pages.add(page);
      });
      finalSources = Array.from(docMap.values()).map((v) => ({
        document_id: v.document_id,
        filename: v.filename,
        pages: Array.from(v.pages).sort((a, b) => a - b),
        page_number: Array.from(v.pages)[0] || 1,
        relevance: v.relevance
      }));
    }

    return {
      isGenerationResult: false,
      generatedDocument: null,
      sourceFilename: null,
      answer,
      isGrounded,
      sources: finalSources,
      chunks,
      query: (res as any).query || p.query,
      task_type: (res as any).task_type,
      model: (res as any).model,
      routing_info: (res as any).routing_info
    };
  }, [p.result, p.query]);

  const handleQuickExportReport = async () => {
    if (!parsedData || !parsedData.query) return;
    setExportingReport(true);
    try {
      const rep = await ragApi.generateReport({
        title: parsedData.query.slice(0, 60),
        topic: parsedData.answer || parsedData.query,
        format: "pdf",
        document_id: p.selectedDocId || undefined
      });
      antMessage.success(`Generated report '${rep.filename}'!`);
      // Download report
      await handleDownloadGenerated(rep);
      if (p.onRefreshDocuments) {
        p.onRefreshDocuments();
      }
    } catch (err: any) {
      antMessage.error(err.message || "Failed exporting report.");
    } finally {
      setExportingReport(false);
    }
  };

  // Selected document helper
  const selectedDocObj = React.useMemo(() => {
    if (!p.selectedDocId) return null;
    return p.documents.find((d) => d.id === p.selectedDocId || d.filename === p.selectedDocId);
  }, [p.documents, p.selectedDocId]);

  return (
    <div className="aegis-view-stack space-y-6">
      {/* Header */}
      <section className="aegis-view-heading flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <Typography.Title level={2} className="!mb-1 !text-slate-100 flex items-center space-x-2.5">
            <BookOutlined className="text-blue-400" />
            <span>Document Intelligence & Knowledge Base</span>
          </Typography.Title>
          <Typography.Paragraph className="!mb-0 text-slate-400 text-sm">
            Ask questions grounded strictly in your indexed organizational documents or generate intelligence reports.
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Tag color="cyan" className="font-mono text-xs">AIR-GAPPED RAG</Tag>
          <Tag color="blue" className="font-mono text-xs">STRICT GROUNDING</Tag>
          <Tag color="success" className="font-mono text-xs">ZERO CLOUD EGRESS</Tag>
        </Space>
      </section>

      <Row gutter={[20, 20]}>
        {/* Main Q&A Column */}
        <Col xs={24} lg={16}>
          <Card
            title={
              <div className="flex items-center justify-between w-full">
                <Space>
                  <RobotOutlined className="text-blue-400" />
                  <span className="font-semibold text-slate-100">Document Analysis Assistant</span>
                </Space>
                {selectedDocObj && (
                  <Tag color="blue" className="font-mono text-[11px]">
                    Scoped: {selectedDocObj.filename}
                  </Tag>
                )}
              </div>
            }
            className="aegis-panel-card shadow-lg bg-[#080d1a] border-slate-800"
          >
            {/* Document Scope Selector & Options */}
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <div className="flex items-center space-x-2 text-xs text-slate-400">
                <FilterOutlined className="text-blue-400" />
                <span className="font-semibold uppercase tracking-wider text-[11px]">Target Scope:</span>
              </div>
              <Select
                value={p.selectedDocId || "ALL"}
                onChange={(val) => {
                  if (p.setSelectedDocId) {
                    p.setSelectedDocId(val === "ALL" ? null : val);
                  }
                }}
                style={{ width: 260 }}
                options={[
                  { label: "All Indexed Documents", value: "ALL" },
                  ...p.documents.map((d) => ({
                    label: `${d.filename} (${d.chunk_count || d.chunks || 0} chunks)`,
                    value: d.id
                  }))
                ]}
                className="bg-[#050811] text-xs"
              />
              <span className="text-[11px] text-slate-500">
                {p.selectedDocId
                  ? "Answers and summaries are restricted strictly to the selected document."
                  : "Searches and synthesizes across all indexed organizational knowledge."}
              </span>
            </div>

            {/* ATTACHED ARTIFACT CARD */}
            {selectedDocObj && (
              <div className="mb-4 p-3.5 bg-[#0a1124] border border-blue-500/30 rounded-xl flex items-center justify-between gap-3 shadow-inner">
                <div className="flex items-center space-x-3 min-w-0">
                  <div className="w-10 h-10 rounded-lg bg-[#050811] border border-slate-700/80 flex items-center justify-center flex-shrink-0">
                    {selectedDocObj.category === "image" || selectedDocObj.mime_type?.startsWith("image/") ? (
                      <PictureOutlined className="text-amber-400 text-lg" />
                    ) : selectedDocObj.category === "presentation" ? (
                      <FilePptOutlined className="text-orange-400 text-lg" />
                    ) : selectedDocObj.category === "spreadsheet" ? (
                      <FileExcelOutlined className="text-emerald-400 text-lg" />
                    ) : selectedDocObj.filename?.endsWith(".pdf") ? (
                      <FilePdfOutlined className="text-red-400 text-lg" />
                    ) : (
                      <FileTextOutlined className="text-blue-400 text-lg" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold text-slate-100 truncate block">
                        {selectedDocObj.filename}
                      </span>
                      <Tag color={selectedDocObj.category === "image" ? "gold" : selectedDocObj.category === "spreadsheet" ? "green" : "blue"} className="font-mono uppercase text-[10px] px-1.5 py-0">
                        {selectedDocObj.category || "DOCUMENT"}
                      </Tag>
                    </div>
                    <div className="flex items-center space-x-3 text-[11px] text-slate-400 mt-0.5 font-mono">
                      <span className="text-emerald-400">● Indexed & Ready</span>
                      {selectedDocObj.file_size ? (
                        <span>{(selectedDocObj.file_size / 1024).toFixed(1)} KB</span>
                      ) : null}
                      <span>{selectedDocObj.chunk_count || selectedDocObj.chunks || 1} chunks</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2 flex-shrink-0">
                  <Button
                    size="small"
                    type="text"
                    onClick={() => {
                      if (p.setSelectedDocId) p.setSelectedDocId(null);
                    }}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Clear Scope
                  </Button>
                </div>
              </div>
            )}

            {/* Question Input Form */}
            <form onSubmit={(e) => { e.preventDefault(); p.onSearch(); }} className="space-y-3">
              <Input.TextArea
                rows={3}
                placeholder="Ask a factual question or request report generation (e.g., 'generate a summary document of sih2026ppt.pdf')..."
                value={p.query}
                onChange={(e) => p.setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    p.onSearch();
                  }
                }}
                className="bg-[#050811] border-slate-700 text-slate-100 placeholder-slate-500 rounded-xl"
              />
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3 text-xs text-slate-400">
                  <span>Context depth:</span>
                  <InputNumber
                    min={1}
                    max={10}
                    value={p.topK}
                    onChange={(v) => p.setTopK(v || 5)}
                    size="small"
                    className="w-16 bg-[#050811] border-slate-700"
                  />
                  <span className="text-slate-500 font-mono text-[11px]">chunks</span>
                </div>
                <Button
                  type="primary"
                  icon={<SearchOutlined />}
                  loading={p.searching}
                  onClick={p.onSearch}
                  className="bg-blue-600 hover:bg-blue-500 font-semibold px-5"
                >
                  Analyze & Synthesize
                </Button>
              </div>
            </form>

            {/* Quick Prompt Suggestions */}
            {p.documents.length > 0 && !parsedData && (
              <div className="mt-4 pt-4 border-t border-slate-800/80">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold mb-2">
                  SUGGESTED GROUNDED QUERIES
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    `Summarize the entire document ${p.documents[0]?.filename || ""}`,
                    `Generate a summary document of ${p.documents[0]?.filename || ""}`,
                    "Extract all operational requirements and specifications",
                    "What are the primary safety protocols and emergency procedures?",
                    "Identify technical risks, constraints, and recommendations"
                  ].map((sug, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => {
                        p.setQuery(sug);
                      }}
                      className="px-2.5 py-1 text-xs bg-[#050811] hover:bg-slate-800/70 text-slate-300 rounded-md border border-slate-800 text-left transition-colors"
                    >
                      {sug}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Error State */}
            {p.queryError && (
              <Alert
                className="mt-4"
                type="error"
                showIcon
                title="Analysis Error"
                description={
                  <div>
                    <p className="mb-2">{p.queryError}</p>
                    <Typography.Text type="secondary" className="text-xs font-mono">
                      Host: http://127.0.0.1:8000
                    </Typography.Text>
                  </div>
                }
                action={
                  <Button size="small" danger onClick={p.onSearch}>
                    Retry
                  </Button>
                }
              />
            )}

            {/* Main Grounded Q&A Content Area */}
            <div className="mt-6">
              {p.searching ? (
                <div className="flex flex-col items-center justify-center p-12 bg-[#050811] rounded-xl border border-slate-800 text-slate-400 space-y-3">
                  <ReloadOutlined spin className="text-2xl text-blue-400" />
                  <span className="text-xs font-mono uppercase tracking-wider text-slate-300">
                    Analyzing document & generating grounded response...
                  </span>
                  <span className="text-[11px] text-slate-500">
                    Computing local cosine similarity and executing local AI synthesis...
                  </span>
                </div>
              ) : parsedData ? (
                <div className="space-y-6">
                  {/* QUESTION CARD */}
                  <div className="p-4 bg-[#050811] border border-slate-800 rounded-xl space-y-2">
                    <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800/80 pb-2">
                      <span className="font-mono uppercase font-bold text-slate-400">REQUEST</span>
                      {selectedDocObj ? (
                        <Tag color="blue" className="text-[10px] font-mono">
                          Scoped: {selectedDocObj.filename}
                        </Tag>
                      ) : (
                        <Tag color="default" className="text-[10px] font-mono">
                          All Indexed Documents
                        </Tag>
                      )}
                    </div>
                    <div className="text-sm font-semibold text-slate-100">{parsedData.query}</div>
                  </div>

                  {/* GENERATED INTELLIGENCE REPORT VIEW */}
                  {parsedData.isGenerationResult && parsedData.generatedDocument ? (
                    <div className="p-5 bg-[#0b1329] border border-blue-500/40 rounded-xl space-y-4 shadow-md">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div className="flex items-center space-x-2">
                          <RobotOutlined className="text-blue-400 text-base" />
                          <span className="text-xs font-bold uppercase tracking-wider text-blue-300">
                            GROUNDED INTELLIGENCE REPORT GENERATED
                          </span>
                        </div>
                        <Tag color="success" icon={<CheckCircleOutlined />} className="text-[11px] font-bold font-mono">
                          READY FOR DOWNLOAD
                        </Tag>
                      </div>

                      <div className="bg-[#050811] p-4 rounded-lg border border-slate-800 space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center space-x-3">
                            {parsedData.generatedDocument.format === "docx" ? (
                              <FileWordOutlined className="text-blue-500 text-3xl" />
                            ) : (
                              <FilePdfOutlined className="text-red-400 text-3xl" />
                            )}
                            <div>
                              <Typography.Text strong className="text-slate-100 block text-base">
                                {parsedData.generatedDocument.title || parsedData.generatedDocument.filename}
                              </Typography.Text>
                              <span className="text-xs text-slate-400 font-mono">
                                Filename: {parsedData.generatedDocument.filename}
                              </span>
                            </div>
                          </div>
                          <Tag
                            color={parsedData.generatedDocument.format === "docx" ? "blue" : "red"}
                            className="font-mono uppercase font-bold text-xs"
                          >
                            {parsedData.generatedDocument.format}
                          </Tag>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-800/80 text-xs">
                          <div>
                            <span className="text-slate-500 block text-[11px]">SOURCE DOCUMENT</span>
                            <span className="text-slate-300 font-medium">
                              {parsedData.sourceFilename || selectedDocObj?.filename || "Indexed Documents"}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[11px]">FILE SIZE</span>
                            <span className="text-slate-300 font-mono">
                              {parsedData.generatedDocument.file_size
                                ? `${(parsedData.generatedDocument.file_size / 1024).toFixed(1)} KB`
                                : "—"}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[11px]">CREATION TIME</span>
                            <span className="text-slate-300 font-mono">
                              {parsedData.generatedDocument.created_at
                                ? new Date(parsedData.generatedDocument.created_at).toLocaleString()
                                : "—"}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-2">
                        <span className="text-xs text-slate-400">
                          Physical document compiled and persisted to sovereign on-premise storage.
                        </span>
                        <Button
                          type="primary"
                          icon={<DownloadOutlined />}
                          onClick={() => handleDownloadGenerated(parsedData.generatedDocument!)}
                          className="bg-blue-600 hover:bg-blue-500 font-semibold"
                        >
                          Download {parsedData.generatedDocument.format.toUpperCase()} Report
                        </Button>
                      </div>
                    </div>
                  ) : (
                    /* AI SYNTHESIZED GROUNDED ANSWER */
                    <div className="p-5 bg-[#0b1329] border border-blue-500/30 rounded-xl space-y-4 shadow-md">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                        <div className="flex items-center space-x-2 flex-wrap">
                          <RobotOutlined className="text-blue-400 text-base" />
                          <span className="text-xs font-bold uppercase tracking-wider text-blue-300 mr-1">
                            AI SYNTHESIZED ANSWER
                          </span>
                          {parsedData.task_type && (
                            <Tag color={parsedData.task_type === "VISION_ANALYSIS" ? "gold" : "purple"} icon={<ThunderboltOutlined />} className="font-mono text-[10px] px-1.5 py-0">
                              {parsedData.task_type}
                            </Tag>
                          )}
                          {parsedData.model && (
                            <Tag color="cyan" className="font-mono text-[10px] px-1.5 py-0">
                              {parsedData.model}
                            </Tag>
                          )}
                          {parsedData.routing_info?.switched && (
                            <Tag color="orange" className="font-mono text-[10px] px-1.5 py-0">
                              Auto-Switched to Vision
                            </Tag>
                          )}
                        </div>
                        <div className="flex items-center space-x-2">
                          {parsedData.isGrounded ? (
                            <Tag color="success" icon={<CheckCircleOutlined />} className="text-[11px] font-bold font-mono">
                              GROUNDED IN DOCUMENTS
                            </Tag>
                          ) : (
                            <Tag color="warning" icon={<ExclamationCircleOutlined />} className="text-[11px] font-bold font-mono">
                              INSUFFICIENT EVIDENCE
                            </Tag>
                          )}
                          {parsedData.isGrounded && (
                            <Button
                              size="small"
                              icon={<FilePdfOutlined />}
                              loading={exportingReport}
                              onClick={handleQuickExportReport}
                              className="bg-[#050811] text-blue-400 border-blue-500/40 hover:border-blue-400 text-xs font-semibold"
                            >
                              Export Report
                            </Button>
                          )}
                        </div>
                      </div>

                      {/* Grounded Answer Body */}
                      <div className="text-slate-100 text-sm leading-relaxed whitespace-pre-wrap font-sans">
                        {parsedData.answer || (
                          parsedData.chunks.length > 0
                            ? `Found ${parsedData.chunks.length} relevant passages. Review evidence below.`
                            : "No data available"
                        )}
                      </div>

                      {/* SOURCES CITATIONS */}
                      {parsedData.sources.length > 0 && (
                        <div className="pt-3 border-t border-slate-800/80 space-y-2">
                          <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                            SOURCES & CITATIONS
                          </div>
                          <div className="flex flex-wrap gap-2.5">
                            {parsedData.sources.map((src, idx) => (
                              <div
                                key={idx}
                                className="px-3 py-1.5 bg-[#050811] border border-slate-700/80 rounded-lg text-xs flex items-center space-x-2 shadow-sm"
                              >
                                <FileTextOutlined className="text-blue-400" />
                                <span className="font-semibold text-slate-200">{src.filename}</span>
                                {src.pages && src.pages.length > 0 ? (
                                  <span className="text-slate-400 font-mono text-[11px]">
                                    Pages {src.pages.join(", ")}
                                  </span>
                                ) : src.page_number ? (
                                  <span className="text-slate-400 font-mono text-[11px]">
                                    Page {src.page_number}
                                  </span>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* EXPANDABLE EVIDENCE PASSAGES */}
                  {parsedData.chunks.length > 0 && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between px-1">
                        <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                          SUPPORTING EVIDENCE ({parsedData.chunks.length} PASSAGES)
                        </span>
                        <Button
                          type="link"
                          size="small"
                          onClick={() => {
                            if (activeEvidenceKeys.length > 0) {
                              setActiveEvidenceKeys([]);
                            } else {
                              setActiveEvidenceKeys(parsedData.chunks.map((_: any, i: number) => `evidence_${i}`));
                            }
                          }}
                          className="text-xs text-blue-400"
                        >
                          {activeEvidenceKeys.length > 0 ? "Collapse All" : "Expand All"}
                        </Button>
                      </div>

                      <Collapse
                        activeKey={activeEvidenceKeys}
                        onChange={(keys) => setActiveEvidenceKeys(typeof keys === "string" ? [keys] : keys)}
                        className="bg-transparent border border-slate-800 rounded-xl overflow-hidden"
                        items={parsedData.chunks.map((chunk: any, idx: number) => {
                          const meta = chunk.metadata || {};
                          const docName = meta.filename || meta.document_name || "Document";
                          const pageNum = meta.page_number ?? 1;
                          const relevance = chunk.relevance || "High";
                          const sim = chunk.similarity ? (chunk.similarity * 100).toFixed(1) : null;

                          return {
                            key: `evidence_${idx}`,
                            label: (
                              <div className="flex items-center justify-between w-full pr-2 text-xs">
                                <div className="flex items-center space-x-2">
                                  <FileTextOutlined className="text-blue-400" />
                                  <span className="font-semibold text-slate-200">{docName}</span>
                                  <Tag color="default" className="text-[10px] font-mono">
                                    Page {pageNum}
                                  </Tag>
                                </div>
                                <div className="flex items-center space-x-2">
                                  {sim && (
                                    <span className="text-[11px] font-mono text-emerald-400">
                                      {sim}% Match
                                    </span>
                                  )}
                                  <Tag
                                    color={relevance === "High" ? "success" : relevance === "Medium" ? "blue" : "warning"}
                                    className="font-mono text-[10px]"
                                  >
                                    {relevance}
                                  </Tag>
                                </div>
                              </div>
                            ),
                            children: (
                              <div className="space-y-3 bg-[#050811] p-3 rounded-lg">
                                <div className="text-slate-300 text-xs leading-relaxed whitespace-pre-wrap font-mono">
                                  {chunk.text}
                                </div>
                                <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-[11px]">
                                  <span className="text-slate-500 font-mono">
                                    Doc ID: {meta.document_id ? meta.document_id.slice(0, 16) + "..." : "—"}
                                  </span>
                                  <Button
                                    size="small"
                                    type="text"
                                    icon={<CopyOutlined />}
                                    onClick={() => handleCopyText(chunk.text)}
                                    className="text-slate-400 hover:text-slate-200"
                                  >
                                    Copy Passage
                                  </Button>
                                </div>
                              </div>
                            )
                          };
                        })}
                      />
                    </div>
                  )}
                </div>
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <span className="text-slate-500 text-xs">
                      Enter a question or generation instruction above to analyze indexed documents.
                    </span>
                  }
                  className="my-12"
                />
              )}
            </div>
          </Card>
        </Col>

        {/* Sidebar Info & Stats */}
        <Col xs={24} lg={8}>
          <div className="space-y-4">
            {/* Knowledge Stats Card */}
            <Card title="Knowledge Base Index" className="aegis-panel-card bg-[#080d1a] border-slate-800">
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Total Indexed Documents:</span>
                  <span className="font-mono font-bold text-slate-100">{p.documents.length}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Total Indexed Chunks:</span>
                  <span className="font-mono font-bold text-slate-100">
                    {p.documents.reduce((acc, d) => acc + (d.chunk_count || d.chunks || 0), 0)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Embedding Engine:</span>
                  <span className="font-mono text-cyan-400">Local BGE-Small (384d)</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Vector Store:</span>
                  <span className="font-mono text-blue-400">Local ChromaDB (Persisted)</span>
                </div>
              </div>
            </Card>

            {/* Audit & Compliance Card */}
            <Card title="Security & Sovereignty" className="aegis-panel-card bg-[#080d1a] border-slate-800">
              <div className="space-y-2.5 text-xs text-slate-400">
                <div className="flex items-start space-x-2">
                  <SafetyCertificateOutlined className="text-emerald-400 mt-0.5" />
                  <span>Queries and synthesis run 100% locally on premise.</span>
                </div>
                <div className="flex items-start space-x-2">
                  <DatabaseOutlined className="text-blue-400 mt-0.5" />
                  <span>Document vectors and chunks are isolated per organizational tenant.</span>
                </div>
                <div className="flex items-start space-x-2">
                  <HistoryOutlined className="text-indigo-400 mt-0.5" />
                  <span>All queries and report generation are cryptographically logged with HMAC-SHA256.</span>
                </div>
              </div>
            </Card>
          </div>
        </Col>
      </Row>
    </div>
  );
}
