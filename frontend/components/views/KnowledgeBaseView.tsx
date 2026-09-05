"use client";

import React, { useState } from "react";
import { Alert, App, Button, Collapse, Empty, Input, InputNumber, Select, Tag, Typography } from "antd";
import {
  BookOutlined, CheckCircleOutlined, CopyOutlined, DatabaseOutlined, DownloadOutlined,
  ExclamationCircleOutlined, FileExcelOutlined, FilePdfOutlined, FilePptOutlined,
  FileTextOutlined, FileWordOutlined, FilterOutlined, ReloadOutlined,
  SafetyCertificateOutlined, SearchOutlined
} from "@ant-design/icons";
import {
  ragApi, DocumentInfo, RagQueryResponse, GroundedAnswerResponse, GroundedSource,
  GeneratedDocument, KnowledgeBaseGenerationResult, RagSearchResult
} from "../../lib/api/rag";
import { env } from "../../lib/config/env";
import { getToken } from "../../lib/security/token";
import type { KnowledgeHistoryItem } from "./HistoryView";
import SafeMarkdown from "../ui/SafeMarkdown";

interface KnowledgeBaseViewProps {
  documents: DocumentInfo[]; loading: boolean; error: string | null; query: string;
  setQuery: (v: string) => void; topK: number; setTopK: (v: number) => void;
  selectedDocId?: string | null; setSelectedDocId?: (id: string | null) => void;
  onSearch: () => void; searching: boolean;
  result: GroundedAnswerResponse | RagQueryResponse | KnowledgeBaseGenerationResult | null;
  queryError: string | null; history?: KnowledgeHistoryItem[];
  onSelectHistory?: (item: KnowledgeHistoryItem) => void; onRefreshDocuments?: () => void;
}

interface SourceReference { documentId?: string; filename?: string; pages?: number[]; pageNumber?: number; }
interface AnswerResult {
  isGenerationResult: false; answer: string; grounded: boolean; query: string;
  sources: SourceReference[]; chunks: RagSearchResult[]; model?: string; durationMs?: number;
}
interface GeneratedReportResult {
  isGenerationResult: true; generatedDocument: GeneratedDocument; sourceFilename?: string; query: string;
}
type DisplayResult = AnswerResult | GeneratedReportResult;

function isGenerationResult(result: NonNullable<KnowledgeBaseViewProps["result"]>): result is KnowledgeBaseGenerationResult {
  return "isGenerationResult" in result && result.isGenerationResult === true;
}

function documentIcon(document: DocumentInfo) {
  if (document.category === "image" || document.mime_type?.startsWith("image/")) return <FileTextOutlined className="text-amber-400 text-lg" />;
  if (document.category === "presentation") return <FilePptOutlined className="text-orange-400 text-lg" />;
  if (document.category === "spreadsheet") return <FileExcelOutlined className="text-emerald-400 text-lg" />;
  if (document.filename.toLowerCase().endsWith(".pdf")) return <FilePdfOutlined className="text-red-400 text-lg" />;
  return <FileTextOutlined className="text-blue-400 text-lg" />;
}

function formatPages(source: SourceReference) {
  const pages = source.pages?.filter(Number.isFinite);
  if (pages?.length) return `Page${pages.length === 1 ? "" : "s"} ${pages.join(", ")}`;
  return source.pageNumber != null ? `Page ${source.pageNumber}` : null;
}

export default function KnowledgeBaseView(p: KnowledgeBaseViewProps) {
  const { message } = App.useApp();
  const [activeEvidenceKeys, setActiveEvidenceKeys] = useState<string[]>([]);
  const [exportingReport, setExportingReport] = useState(false);

  const handleCopyText = async (text: string) => {
    try { await navigator.clipboard.writeText(text); message.success("Evidence copied to clipboard"); }
    catch { message.error("Unable to copy evidence to the clipboard."); }
  };

  const handleDownloadGenerated = async (doc: GeneratedDocument) => {
    try {
      const token = getToken();
      const response = await fetch(`${env.apiUrl}/documents/generated/${doc.id}/download`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!response.ok) throw new Error("Download failed");
      const url = window.URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = doc.filename; document.body.appendChild(anchor); anchor.click();
      window.URL.revokeObjectURL(url); document.body.removeChild(anchor); message.success(`Downloaded ${doc.filename}`);
    } catch (error: unknown) { message.error(error instanceof Error ? error.message : "Failed downloading generated document."); }
  };

  const displayResult = React.useMemo<DisplayResult | null>(() => {
    if (!p.result) return null;
    if (isGenerationResult(p.result)) return { isGenerationResult: true, generatedDocument: p.result.generatedDocument, sourceFilename: p.result.sourceFilename, query: p.result.query };
    const sources: SourceReference[] = "sources" in p.result
      ? p.result.sources.map((source: GroundedSource) => ({ documentId: source.document_id, filename: source.filename, pages: source.pages, pageNumber: source.page_number }))
      : p.result.results.map((chunk) => ({ documentId: chunk.metadata.document_id, filename: chunk.metadata.filename || chunk.metadata.document_name, pageNumber: chunk.metadata.page_number }));
    return {
      isGenerationResult: false,
      answer: "answer" in p.result ? p.result.answer : "",
      grounded: "grounded" in p.result && p.result.grounded,
      query: p.result.query,
      sources,
      chunks: "results" in p.result ? p.result.results ?? [] : [],
      model: "model" in p.result ? p.result.model : undefined,
      durationMs: "duration_ms" in p.result ? p.result.duration_ms : undefined
    };
  }, [p.result]);

  const selectedDocument = React.useMemo(() => !p.selectedDocId ? null : p.documents.find((document) => document.id === p.selectedDocId || document.filename === p.selectedDocId) ?? null, [p.documents, p.selectedDocId]);

  const handleQuickExportReport = async () => {
    if (!displayResult || displayResult.isGenerationResult || !displayResult.grounded || !displayResult.query) return;
    setExportingReport(true);
    try {
      const generatedDocument = await ragApi.generateReport({ title: displayResult.query.slice(0, 60), topic: displayResult.answer || displayResult.query, format: "pdf", document_id: p.selectedDocId || displayResult.sources[0]?.documentId || undefined });
      message.success(`Generated report '${generatedDocument.filename}'.`);
      await handleDownloadGenerated(generatedDocument);
      p.onRefreshDocuments?.();
    } catch (error: unknown) { message.error(error instanceof Error ? error.message : "Failed generating report."); }
    finally { setExportingReport(false); }
  };

  const technicalItems = !displayResult || displayResult.isGenerationResult ? [] : [
    displayResult.model ? ["Model", displayResult.model] : null,
    displayResult.durationMs != null ? ["Duration", `${displayResult.durationMs} ms`] : null
  ].filter((item): item is [string, string] => item !== null);

  return <div className="aegis-view-stack mx-auto max-w-6xl space-y-7">
    <section className="aegis-view-heading border-b border-slate-800/80 pb-4">
      <Typography.Title level={2} className="!mb-1 !text-slate-100 flex items-center gap-2.5"><BookOutlined className="text-blue-400" />Knowledge Base</Typography.Title>
      <Typography.Paragraph className="!mb-0 max-w-2xl text-sm text-slate-400">Ask questions against your authorized organizational documents and inspect grounded evidence.</Typography.Paragraph>
    </section>

    {p.error && <Alert type="error" showIcon title="Unable to load authorized documents" description={p.error} action={p.onRefreshDocuments ? <Button size="small" danger onClick={p.onRefreshDocuments}>Try again</Button> : undefined} />}

    <section aria-labelledby="knowledge-document-heading" className="space-y-3">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400"><FilterOutlined className="text-blue-400" /><span id="knowledge-document-heading">Document</span></div>
      <Select aria-label="Authorized document scope" value={p.selectedDocId || "ALL"} onChange={(value) => p.setSelectedDocId?.(value === "ALL" ? null : value)} disabled={p.loading || p.documents.length === 0} loading={p.loading} showSearch optionFilterProp="label" className="w-full max-w-2xl" options={[{ label: "All authorized documents", value: "ALL" }, ...p.documents.map((document) => ({ label: document.filename, value: document.id }))]} />
      {selectedDocument ? <div className="flex items-center justify-between gap-4 border border-slate-700/80 bg-slate-900/50 px-4 py-3">
        <div className="flex min-w-0 items-center gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center border border-slate-700/80 bg-[#080d1a]">{documentIcon(selectedDocument)}</span><div className="min-w-0"><div className="truncate text-sm font-semibold text-slate-100">{selectedDocument.filename}</div><div className="mt-0.5 text-xs text-slate-400">Authorized document</div>{(selectedDocument.status || selectedDocument.owner_department_name || selectedDocument.visibility) && <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">{selectedDocument.status && <span>{selectedDocument.status}</span>}{selectedDocument.owner_department_name && <span>{selectedDocument.owner_department_name}</span>}{selectedDocument.visibility && <span>{selectedDocument.visibility}</span>}</div>}</div></div>
        <Button type="text" size="small" onClick={() => p.setSelectedDocId?.(null)}>Clear</Button>
      </div> : p.documents.length === 0 && !p.loading ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No authorized documents available." className="!my-6" /> : <p className="text-xs text-slate-500">Analysis uses documents returned for your account.</p>}
    </section>

    <section aria-labelledby="knowledge-question-heading" className="border-y border-slate-800/80 py-5">
      <div id="knowledge-question-heading" className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Ask a question</div>
      <form onSubmit={(event) => { event.preventDefault(); p.onSearch(); }} className="space-y-3">
        <Input.TextArea aria-label="Question for authorized documents" rows={3} placeholder="Ask a question about your authorized documents" value={p.query} onChange={(event) => p.setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); p.onSearch(); } }} className="bg-[#080d1a] border-slate-700 text-slate-100 placeholder-slate-500" />
        <div className="flex flex-wrap items-center justify-between gap-3"><label className="flex items-center gap-2 text-xs text-slate-500">Retrieval depth<InputNumber min={1} max={10} value={p.topK} onChange={(value) => value != null && p.setTopK(value)} size="small" /></label><Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={p.searching} disabled={p.documents.length === 0}>Ask AEGIS</Button></div>
      </form>
    </section>

    {p.queryError && <Alert type="error" showIcon title="Unable to analyze the selected document" description={p.queryError} action={<Button size="small" danger onClick={p.onSearch}>Try again</Button>} />}

    {p.searching ? <section className="flex min-h-48 flex-col items-center justify-center gap-3 border border-slate-800 bg-[#080d1a] text-center"><ReloadOutlined spin className="text-xl text-blue-400" /><div><div className="text-sm font-medium text-slate-200">Analyzing authorized documents…</div><p className="mt-1 text-xs text-slate-500">This may take a moment.</p></div></section>
      : displayResult?.isGenerationResult ? <section aria-labelledby="generated-report-heading" className="space-y-4 border border-slate-700/80 bg-[#080d1a] p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><div id="generated-report-heading" className="text-xs font-semibold uppercase tracking-wider text-slate-400">Report generated</div><div className="mt-1 text-base font-semibold text-slate-100">{displayResult.generatedDocument.title || displayResult.generatedDocument.filename}</div></div><Tag color="success" icon={<CheckCircleOutlined />}>Ready for download</Tag></div><div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 pt-4"><div className="flex items-center gap-2 text-xs text-slate-400">{displayResult.generatedDocument.format === "docx" ? <FileWordOutlined className="text-blue-400" /> : <FilePdfOutlined className="text-red-400" />}<span>{displayResult.generatedDocument.filename}</span>{displayResult.generatedDocument.format && <span className="uppercase">{displayResult.generatedDocument.format}</span>}</div><Button type="primary" icon={<DownloadOutlined />} onClick={() => handleDownloadGenerated(displayResult.generatedDocument)}>Download report</Button></div></section>
      : displayResult ? <div className="space-y-6">
        <section className="border-l-2 border-blue-500 pl-4"><div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Question</div><p className="mt-2 text-sm font-medium text-slate-200">{displayResult.query}</p></section>
        <section aria-labelledby="knowledge-answer-heading" className="border-y border-slate-800/80 py-6"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><div id="knowledge-answer-heading" className="text-xs font-semibold uppercase tracking-wider text-slate-400">Answer</div>{displayResult.grounded ? <Tag color="success" icon={<CheckCircleOutlined />}>Grounded answer</Tag> : <Tag color="warning" icon={<ExclamationCircleOutlined />}>Insufficient evidence</Tag>}</div>{displayResult.model && <span className="text-xs text-slate-500">Local model · {displayResult.model}</span>}</div>{displayResult.grounded ? (displayResult.answer ? <SafeMarkdown content={displayResult.answer} /> : <p className="text-sm text-slate-400">No synthesized answer was returned.</p>) : <div className="max-w-2xl text-sm leading-6 text-slate-300">AEGIS could not find sufficient evidence in the authorized document scope to answer this question.</div>}</section>
        {displayResult.grounded && displayResult.sources.length > 0 && <section aria-labelledby="knowledge-sources-heading" className="space-y-2"><div id="knowledge-sources-heading" className="text-xs font-semibold uppercase tracking-wider text-slate-400">Sources</div><div className="divide-y divide-slate-800 border-y border-slate-800">{displayResult.sources.map((source, index) => { const pages = formatPages(source); return <div key={`${source.filename ?? "source"}-${index}`} className="flex items-center gap-3 py-3 text-sm"><span className="w-16 shrink-0 text-xs font-medium text-slate-500">Source {index + 1}</span><FileTextOutlined className="text-blue-400" /><span className="min-w-0 truncate text-slate-200">{source.filename ?? "Source details unavailable"}</span>{pages && <span className="ml-auto shrink-0 text-xs text-slate-500">{pages}</span>}</div>; })}</div></section>}
        {displayResult.grounded && <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 pt-5"><Button icon={<FilePdfOutlined />} loading={exportingReport} onClick={handleQuickExportReport}>{exportingReport ? "Generating report…" : "Generate report"}</Button><span className="text-xs text-slate-500">Generated from the current grounded result.</span></div>}
        {displayResult.chunks.length > 0 && <section aria-labelledby="knowledge-evidence-heading"><Collapse className="border-slate-800 bg-transparent" activeKey={activeEvidenceKeys} onChange={(keys) => setActiveEvidenceKeys(typeof keys === "string" ? [keys] : keys)} items={[{ key: "evidence", label: <span id="knowledge-evidence-heading" className="text-xs font-semibold uppercase tracking-wider text-slate-300">Evidence ({displayResult.chunks.length})</span>, children: <div className="space-y-4">{displayResult.chunks.map((chunk, index) => { const sourceName = chunk.metadata.filename || chunk.metadata.document_name; const page = chunk.metadata.page_number; return <article key={chunk.chunk_id || `evidence-${index}`} className="border-b border-slate-800 pb-4 last:border-0"><div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs"><div className="flex items-center gap-2 text-slate-400"><span className="font-medium text-slate-300">Evidence {index + 1}</span>{sourceName && <span>{sourceName}</span>}{page != null && <span>Page {page}</span>}</div><Button size="small" type="text" icon={<CopyOutlined />} onClick={() => handleCopyText(chunk.text)}>Copy</Button></div><div className="whitespace-pre-wrap break-words bg-[#080d1a] p-3 font-mono text-xs leading-6 text-slate-300">{chunk.text}</div></article>; })}</div> }]}/></section>}
        <Collapse className="border-slate-800 bg-transparent" items={[...(technicalItems.length > 0 ? [{ key: "technical", label: "Retrieval details", children: <dl className="space-y-2 text-xs">{technicalItems.map(([label, value]) => <div key={label} className="flex gap-4"><dt className="w-24 text-slate-500">{label}</dt><dd className="text-slate-300">{value}</dd></div>)}</dl> }] : []), { key: "security", label: "Security & sovereignty", children: <div className="space-y-2 text-xs leading-5 text-slate-400"><p><SafetyCertificateOutlined className="mr-2 text-emerald-400" />Only documents returned for your account are available in this workspace.</p><p><DatabaseOutlined className="mr-2 text-blue-400" />Document authorization and retrieval are enforced by the backend.</p></div> }]} />
      </div> : <section className="border border-slate-800 bg-[#080d1a] py-10"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={p.documents.length === 0 ? "No authorized documents available." : "Select an authorized document or ask a question to begin analysis."} /></section>}
  </div>;
}
