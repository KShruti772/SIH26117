import { apiFetch } from "./client";

export interface DocumentInfo {
  id: string;
  filename: string;
  status: string;
  uploaded_at: number;
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
   * POST /documents/upload
   * Ingests a new document file via multipart/form-data.
   */
  async ingestDocument(file: File): Promise<DocumentInfo> {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<DocumentInfo>("/documents/upload", {
      method: "POST",
      body: formData,
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
