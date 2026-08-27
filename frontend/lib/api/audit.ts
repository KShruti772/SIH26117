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
  }
};
