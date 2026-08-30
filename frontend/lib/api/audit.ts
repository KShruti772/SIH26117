import { apiFetch } from "./client";

export interface AuditLog {
  id: number;
  timestamp: string;
  user_id: number | null;
  username: string | null;
  role: string | null;
  action: string;
  component: string;
  resource: string | null;
  status: "success" | "failure";
  request_id: string | null;
  duration_ms: number | null;
  metadata_json: string | null;
}

export interface AuditQueryParams {
  action?: string;
  username?: string;
  status?: "success" | "failure";
  request_id?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
}

export interface AuditSummary {
  total_events: number;
  successful_events: number;
  failed_actions: number;
  security_events: number;
  ai_operations: number;
  rag_events: number;
  sandbox_events: number;
  authentication?: number;
}

/**
 * Discovered Backend API: Audit Ledger services
 */
export const auditApi = {
  /**
   * GET /audit
   * Retrieves system audit logs. Restricted strictly to admin role check on backend.
   */
  async getLogs(params: AuditQueryParams = {}): Promise<AuditLog[]> {
    return apiFetch<AuditLog[]>("/audit", {
      method: "GET",
      params: params as Record<string, string>,
    });
  },

  /**
   * GET /audit/summary
   * Retrieves real counts from SQLite database for dashboard. Restricted to admin role.
   */
  async getSummary(): Promise<AuditSummary> {
    return apiFetch<AuditSummary>("/audit/summary", {
      method: "GET",
    });
  }
};
