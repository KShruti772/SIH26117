import { apiFetch } from "./client";

export interface DocumentInfo {
  id: string;
  filename: string;
  status: string;
  uploaded_at: number | string;
  chunk_count?: number;
  chunks?: number;
  pages?: number;
  page_count?: number;
  file_size?: number;
  category?: string;
  document_type?: string;
  file_type?: string;
  mime_type?: string;
  extraction_method?: string;
  metadata?: Record<string, any>;
  embedding_model?: string;
  owner_username?: string;
}

export interface RagSearchResult {
  chunk_id: string;
  text: string;
  distance: number;
  similarity?: number;
  relevance?: string;
  metadata: {
    document_id: string;
    filename: string;
    document_name?: string;
    page_number?: number;
    chunk_index?: number;
    section?: string;
    embedding_model?: string;
    is_mock?: boolean;
    owner_id?: number;
    owner_username?: string;
  };
}

export interface RagQueryResponse {
  query: string;
  results: RagSearchResult[];
  count: number;
}

export interface GroundedSource {
  document_id: string;
  filename: string;
  page_number?: number;
  pages?: number[];
  relevance?: string;
  distance?: number;
  similarity?: number;
}

export interface GroundedAnswerResponse {
  answer: string;
  sources: GroundedSource[];
  grounded: boolean;
  query: string;
  session_id?: string;
  results?: RagSearchResult[];
  duration_ms?: number;
  task_type?: string;
  model?: string;
  routing_info?: any;
}

export interface DocumentStats {
  total_documents: number;
  indexed_documents: number;
  failed_documents: number;
  processing_documents: number;
  total_chunks: number;
  total_file_size: number;
}

export interface GeneratedDocument {
  id: string;
  owner_id?: number;
  owner_username?: string;
  filename: string;
  title: string;
  format: string;
  file_size: number;
  mime_type: string;
  source_document_ids?: string[];
  conversation_id?: string;
  status: string;
  created_at: string;
}

export interface GenerateReportPayload {
  title: string;
  topic?: string;
  format?: string;
  document_id?: string;
  session_id?: string;
}

export interface KnowledgeBaseGenerationResult {
  isGenerationResult: true;
  generatedDocument: GeneratedDocument;
  sourceFilename?: string;
  query: string;
}

export const ragApi = {
  /**
   * GET /documents
   * Lists all indexed documents in the local vector database.
   */
  async listDocuments(): Promise<DocumentInfo[]> {
    return apiFetch<DocumentInfo[]>("/documents", {
      method: "GET",
    });
  },

  /**
   * GET /documents/stats
   * Retrieves authoritative document counts and chunk statistics.
   */
  async getStats(): Promise<DocumentStats> {
    return apiFetch<DocumentStats>("/documents/stats", {
      method: "GET",
    });
  },

  /**
   * POST /documents/upload
   * Ingests a new document file via multipart/form-data.
   */
  async ingestDocument(file: File): Promise<DocumentInfo> {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<DocumentInfo>("/documents/upload", {
      method: "POST",
      body: formData,
      timeoutMs: 180000,
    });
  },

  /**
   * POST /documents/ask
   * Generates a verified, document-grounded AI answer with citations.
   */
  async askDocument(query: string, documentId?: string, sessionId?: string, topK: number = 5): Promise<GroundedAnswerResponse> {
    return apiFetch<GroundedAnswerResponse>("/documents/ask", {
      method: "POST",
      body: JSON.stringify({
        query,
        document_id: documentId || undefined,
        session_id: sessionId || undefined,
        top_k: topK,
      }),
      timeoutMs: 120000,
    });
  },

  /**
   * POST /documents/generate
   * Generates a physical grounded intelligence report (PDF/DOCX).
   */
  async generateReport(payload: GenerateReportPayload): Promise<GeneratedDocument> {
    return apiFetch<GeneratedDocument>("/documents/generate", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: 180000,
    });
  },

  /**
   * GET /documents/generated
   * Lists all generated intelligence reports.
   */
  async listGeneratedDocuments(): Promise<GeneratedDocument[]> {
    return apiFetch<GeneratedDocument[]>("/documents/generated", {
      method: "GET",
    });
  },

  /**
   * DELETE /documents/generated/{id}
   * Removes a generated report from storage.
   */
  async deleteGeneratedDocument(id: string): Promise<{ status: string; message: string }> {
    return apiFetch<{ status: string; message: string }>(`/documents/generated/${id}`, {
      method: "DELETE",
    });
  },

  /**
   * POST /documents/query
   * Executes similarity search query against vector database.
   */
  async query(query: string, topK: number = 3): Promise<RagQueryResponse> {
    return apiFetch<RagQueryResponse>("/documents/query", {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK }),
      timeoutMs: 120000,
    });
  },

  /**
   * POST /documents/{id}/index
   * Triggers manual re-indexing of a document.
   */
  async reindexDocument(id: string): Promise<{ id: string; status: string; message: string }> {
    return apiFetch<{ id: string; status: string; message: string }>(`/documents/${id}/index`, {
      method: "POST",
    });
  },

  /**
   * DELETE /documents/{id}
   * Removes vector mappings and deletes physical document storage.
   */
  async deleteDocument(id: string): Promise<{ status: string; message: string }> {
    return apiFetch<{ status: string; message: string }>(`/documents/${id}`, {
      method: "DELETE",
    });
  }
};
