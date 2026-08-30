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
  duration_ms: number;
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
