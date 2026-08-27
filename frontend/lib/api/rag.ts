/**
 * RAG / Knowledge Base API Stubs
 * 
 * DESIGN NOTICE:
 * These stubs represent client-side interfaces that will map to future backend endpoints.
 * The underlying local RAG logic (DocumentLoader, RecursiveTextSplitter, Chroma vector DB)
 * is already verified on the backend, and will be exposed through API routers in a future task.
 */

export interface DocumentInfo {
  document_id: string;
  filename: string;
  source_path: string;
  ingested_at: number;
}

export interface SearchResult {
  chunk_id: string;
  text: string;
  distance: number;
  metadata: {
    document_id: string;
    filename: string;
    page_number: number;
    chunk_id: string;
  };
}

export const ragApi = {
  /**
   * Future GET /api/rag/documents
   * Lists all indexed documents.
   */
  async listDocuments(): Promise<DocumentInfo[]> {
    console.warn("RAG API: listDocuments stub invoked.");
    return [];
  },

  /**
   * Future POST /api/rag/ingest
   * Ingests a new document file.
   */
  async ingestDocument(file: File): Promise<{ document_id: string; filename: string }> {
    console.warn("RAG API: ingestDocument stub invoked.", file.name);
    return { document_id: "stub-id", filename: file.name };
  },

  /**
   * Future POST /api/rag/search
   * Performs vector similarity search.
   */
  async search(query: string, topK: number = 3): Promise<SearchResult[]> {
    console.warn("RAG API: search stub invoked.", query);
    return [];
  }
};
