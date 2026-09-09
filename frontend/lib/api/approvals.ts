import { apiFetch } from "./client";

export type ApprovalStatusType =
  | "PENDING"
  | "WAITING_FOR_HUMAN"
  | "APPROVED"
  | "MODIFIED"
  | "REJECTED"
  | "EXPIRED"
  | "FAILED";

export type ApprovalActionType = "DOCUMENT_APPROVAL" | string;

export interface ApprovalItem {
  id: string;
  approval_id: string;
  action_type: ApprovalActionType;
  status: ApprovalStatusType;
  plan_id?: string;
  step_id?: string;
  conversation_id?: string;
  requester_id?: number;
  requester_username?: string;
  reviewer_id?: number | null;
  reviewer_username?: string | null;
  reviewer_role?: string | null;
  department_id?: number;
  department_name?: string;
  created_at: string;
  reviewed_at?: string | null;
  expires_at?: string | null;
  summary: string;
  target_format?: string;
  findings_preview?: string | null;
  calculations_preview?: string | null;
  rejection_reason?: string | null;
}

export interface ApprovalDetail extends ApprovalItem {
  proposed_payload?: {
    summary?: string;
    findings?: string;
    calculations?: string;
    draft_document_text?: string;
    target_format?: string;
    plan_id?: string;
    step_id?: string;
    conversation_id?: string;
    plan_snapshot?: {
      plan_id?: string;
      request?: string;
      category?: string;
      status?: string;
      conversation_id?: string;
      current_step_index?: number;
      steps?: Array<{
        step_id: string;
        step_type: string;
        status: string;
        input?: Record<string, any>;
        output?: any;
        observation?: any;
      }>;
    };
    sources?: Array<{
      filename?: string;
      page_number?: number;
      text?: string;
      distance?: number;
    }>;
    [key: string]: any;
  };
  modified_payload?: {
    modifications?: Record<string, any>;
    revised_text?: string;
    comment?: string;
    notes?: string;
    [key: string]: any;
  } | null;
}

export interface ApprovalListResponse {
  success: boolean;
  total: number;
  approvals: ApprovalItem[];
}

export interface ApprovalDetailResponse {
  success: boolean;
  approval: ApprovalDetail;
}

export interface ApprovalDecisionPayload {
  comment?: string;
}

export interface ApprovalModifyPayload {
  modifications?: Record<string, any>;
  revised_text?: string;
  comment?: string;
}

export interface ApprovalRejectPayload {
  reason: string;
}

export interface ApprovalResumePayload {
  conversation_id?: string;
}

export interface GeneratedArtifactInfo {
  id?: string;
  filename: string;
  title?: string;
  format: string;
  file_path?: string;
  file_size?: number;
  mime_type?: string;
  artifact_path?: string;
}

export interface ApprovalResolutionResult {
  success: boolean;
  approval_id: string;
  status: ApprovalStatusType;
  message: string;
  rejection_reason?: string;
  execution?: {
    status?: string;
    verification?: string;
    tools_used?: string[];
    replan_count?: number;
    artifact?: GeneratedArtifactInfo;
    artifacts?: GeneratedArtifactInfo[];
    approval_id?: string;
    [key: string]: any;
  };
}

/**
 * Authoritative Backend API Client: Human-in-the-Loop Approvals
 */
export const approvalsApi = {
  /**
   * GET /api/approvals/pending
   * Lists pending approval requests visible to the authenticated reviewer.
   */
  async listPending(params?: { department_id?: number; limit?: number }): Promise<ApprovalListResponse> {
    const queryParams: Record<string, string> = { status: "WAITING_FOR_HUMAN" };
    if (params?.department_id !== undefined) {
      queryParams.department_id = String(params.department_id);
    }
    if (params?.limit !== undefined) {
      queryParams.limit = String(params.limit);
    }
    return apiFetch<ApprovalListResponse>("/api/approvals/pending", {
      method: "GET",
      params: queryParams,
    });
  },

  /**
   * GET /api/approvals
   * Lists all approval requests with optional status and department filters.
   */
  async listAll(params?: {
    status?: string;
    department_id?: number;
    limit?: number;
  }): Promise<ApprovalListResponse> {
    const queryParams: Record<string, string> = {};
    if (params?.status) {
      queryParams.status = params.status;
    }
    if (params?.department_id !== undefined) {
      queryParams.department_id = String(params.department_id);
    }
    if (params?.limit !== undefined) {
      queryParams.limit = String(params.limit);
    }
    return apiFetch<ApprovalListResponse>("/api/approvals", {
      method: "GET",
      params: queryParams,
    });
  },

  /**
   * GET /api/approvals/{approval_id}
   * Retrieves full details and decision-relevant evidence for an approval request.
   */
  async getById(approvalId: string): Promise<ApprovalDetailResponse> {
    return apiFetch<ApprovalDetailResponse>(`/api/approvals/${encodeURIComponent(approvalId)}`, {
      method: "GET",
    });
  },

  /**
   * POST /api/approvals/{approval_id}/approve
   * Approves a pending request and resumes sovereign agent execution to compile deliverables.
   */
  async approve(
    approvalId: string,
    payload?: ApprovalDecisionPayload
  ): Promise<ApprovalResolutionResult> {
    return apiFetch<ApprovalResolutionResult>(`/api/approvals/${encodeURIComponent(approvalId)}/approve`, {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
  },

  /**
   * POST /api/approvals/{approval_id}/modify
   * Modifies a pending request with reviewer constraints, triggering automated replanning.
   */
  async modify(
    approvalId: string,
    payload: ApprovalModifyPayload
  ): Promise<ApprovalResolutionResult> {
    return apiFetch<ApprovalResolutionResult>(`/api/approvals/${encodeURIComponent(approvalId)}/modify`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * POST /api/approvals/{approval_id}/reject
   * Rejects a pending request with a mandatory reason, safely halting the workflow.
   */
  async reject(
    approvalId: string,
    payload: ApprovalRejectPayload
  ): Promise<ApprovalResolutionResult> {
    return apiFetch<ApprovalResolutionResult>(`/api/approvals/${encodeURIComponent(approvalId)}/reject`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * POST /api/approvals/{approval_id}/resume
   * Explicitly resumes execution for an already approved/modified request idempotently.
   */
  async resume(
    approvalId: string,
    payload?: ApprovalResumePayload
  ): Promise<ApprovalResolutionResult> {
    return apiFetch<ApprovalResolutionResult>(`/api/approvals/${encodeURIComponent(approvalId)}/resume`, {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
  },
};
