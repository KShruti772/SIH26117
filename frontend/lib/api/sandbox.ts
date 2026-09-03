import { apiFetch } from "./client";

export interface SandboxExecutionPayload {
  code: string;
  timeout_seconds?: number;
}

export interface SandboxExecutionResponse {
  success: boolean;
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  duration_ms: number | null;
  execution_id?: string;
  execution_time_ms?: number | null;
  code_hash?: string;
  language?: string;
  timestamp?: string;
  error: string | null;
}

export const sandboxApi = {
  /**
   * Submits python scripts to the backend for sandboxed execution inside the subprocess container.
   */
  async execute(payload: SandboxExecutionPayload): Promise<SandboxExecutionResponse> {
    return apiFetch<SandboxExecutionResponse>("/sandbox/execute", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }
};
