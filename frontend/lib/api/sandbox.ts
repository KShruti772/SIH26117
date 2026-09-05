import { apiFetch } from "./client";

export interface SandboxExecutionPayload {
  code: string;
  timeout_seconds?: number;
  script_filename?: string;
  conversation_id?: string;
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
  artifacts?: Array<{
    id: string;
    filename: string;
    file_size: number;
    mime_type: string;
  }>;
}

export interface SandboxFileRecord {
  id: string;
  filename: string;
  file_path: string;
  file_size: number;
  lines_count: number;
  sha256_hash: string;
  mime_type: string;
  user_id: number;
  username: string;
  conversation_id: string;
  created_at: string;
  content?: string;
}

export interface SandboxExecutionRecord {
  id: string;
  user_id: number;
  username: string;
  conversation_id: string;
  script_filename: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  duration_ms: number;
  sha256_hash: string;
  lines_count: number;
  artifacts_count: number;
  artifacts_json?: string;
  created_at: string;
  code?: string;
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
  },

  /**
   * Lists sandbox files created in the workspace.
   */
  async getFiles(): Promise<SandboxFileRecord[]> {
    return apiFetch<SandboxFileRecord[]>("/sandbox/files");
  },

  /**
   * Gets details and content of a specific sandbox file.
   */
  async getFile(fileId: string): Promise<SandboxFileRecord> {
    return apiFetch<SandboxFileRecord>(`/sandbox/files/${fileId}`);
  },

  /**
   * Lists past sandbox execution records.
   */
  async getExecutions(limit: number = 50): Promise<SandboxExecutionRecord[]> {
    return apiFetch<SandboxExecutionRecord[]>(`/sandbox/executions?limit=${limit}`);
  },

  /**
   * Gets details of a specific execution run.
   */
  async getExecution(executionId: string): Promise<SandboxExecutionRecord> {
    return apiFetch<SandboxExecutionRecord>(`/sandbox/executions/${executionId}`);
  }
};
