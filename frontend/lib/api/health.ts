import { apiFetch } from "./client";

export interface SystemHealthResponse {
  status: string;
  services: {
    ai_runtime: "healthy" | "degraded";
    rag_engine: "healthy" | "unhealthy";
    vector_store: "healthy" | "unhealthy";
    sandbox: "protected";
    audit_ledger: "active" | "inactive";
  };
}

export const healthApi = {
  /**
   * GET /health
   * Retrieves live checks for all local system services.
   */
  async getHealth(): Promise<SystemHealthResponse> {
    return apiFetch<SystemHealthResponse>("/health?details=true", {
      method: "GET",
    });
  }
};
