/**
 * Isolated Python Sandbox Execution API Stubs
 * 
 * DESIGN NOTICE:
 * These stubs represent client-side interfaces that will map to future backend endpoints.
 * The subprocess-based code execution sandbox is verified on the backend, and will
 * be exposed via API routers in a future task.
 */

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
   * Future POST /api/sandbox/execute
   * Submits untrusted Python scripts for sandboxed execution.
   */
  async execute(payload: SandboxExecutionPayload): Promise<SandboxExecutionResponse> {
    console.warn("Sandbox API: execute stub invoked.");
    return {
      success: true,
      exit_code: 0,
      stdout: "Sandbox execution stub output.",
      stderr: "",
      timed_out: false,
      duration_ms: 5,
      error: null
    };
  }
};
