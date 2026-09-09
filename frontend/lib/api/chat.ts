import { apiFetch, ApiError } from "./client";
import { env } from "../config/env";
import { getToken } from "../security/token";

export interface RoutingTelemetry {
  task_type?: string;
  selected_model?: string;
  routing?: string;
  switched?: boolean;
  reason?: string;
  rag_used?: boolean;
  verification_status?: string;
  required_capabilities?: string[];
  matched_capabilities?: string[];
}

export interface SandboxArtifact {
  id: string;
  filename: string;
  file_size: number;
  mime_type: string;
  content_hash: string;
  download_url: string;
  created_at: string;
}

export interface SandboxExecutionResult {
  execution_id?: string;
  success: boolean;
  status: "SUCCESS" | "FAILED";
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out?: boolean;
  duration_ms: number;
  code?: string;
  artifacts?: SandboxArtifact[];
  error?: string;
}

export interface ExecutionEvent {
  event_type: string;
  execution_id: string;
  timestamp: string;
  session_id?: string;
  step_id?: number;
  step_type?: string;
  message?: string;
  metadata?: Record<string, any>;
}

export interface PlanStep {
  step_id: number;
  description: string;
  capability?: string;
  step_type?: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "SKIPPED";
  duration_ms?: number;
  selected_model?: string;
  verification_state?: string;
  verification_result?: string;
  is_replan?: boolean;
  replan_count?: number;
  observation?: string;
  output_summary?: string;
}

export interface ExecutionPlan {
  plan_id?: string;
  goal?: string;
  status?: string;
  steps: PlanStep[];
  final_output?: any;
}

export interface ChatResponse {
  success: boolean;
  session_id?: string;
  answer: string;
  sources: Array<{ filename: string; page_number: number; text?: string; distance?: number }>;
  verification: string;
  request_id: string;
  duration_ms: number;
  rag_used?: boolean;
  execution_id?: string;
  execution_events?: ExecutionEvent[];
  plan?: ExecutionPlan;
  plan_id?: string;
  approval_id?: string;
  agent_state?: string;
  is_waiting_for_human?: boolean;
  artifact?: any;
  artifacts?: any[];
  metadata?: Record<string, any>;
  sandbox_execution?: SandboxExecutionResult;
  model_info?: {
    model_id: string;
    inference_mode: string;
  };
  routing_info?: RoutingTelemetry;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  rag_used?: boolean;
  sources?: Array<{ filename: string; page_number: number; text?: string; distance?: number }>;
  model_id?: string;
  duration_ms?: number;
  request_id?: string;
  verification?: string;
  error_detail?: string;
  task_type?: string;
  document_ids?: string[];
  execution_id?: string;
  execution_events?: ExecutionEvent[];
  plan?: ExecutionPlan;
  metadata?: Record<string, any>;
  routing_info?: RoutingTelemetry;
  sandbox_execution?: SandboxExecutionResult;
}

export interface ConversationSession {
  id: string;
  title: string;
  feature?: string;
  status?: string;
  created_at: string;
  updated_at: string;
  last_message_at?: string;
  messages?: ConversationMessage[];
}

export interface ConversationExecutionStatus {
  success: boolean;
  session_id: string;
  execution_status: string; // "PLANNING" | "EXECUTING" | "VERIFYING" | "WAITING_FOR_HUMAN" | "APPROVED" | "MODIFIED" | "REJECTED" | "COMPLETED" | "FAILED" | "IDLE"
  approval_id?: string;
  approval_status?: string;
  plan_id?: string;
  agent_state?: string;
  is_waiting_for_human?: boolean;
  rejection_reason?: string;
  has_artifact?: boolean;
  artifact?: {
    artifact_id?: string;
    artifact_name?: string;
    artifact_path?: string;
    format?: string;
    mime_type?: string;
    download_url?: string;
  };
  total_messages: number;
}

/**
 * Discovered Backend API: Agent Operations & Session Management
 */
export const chatApi = {
  /**
   * GET /conversations
   * Lists saved conversations for active user.
   */
  async listConversations(): Promise<ConversationSession[]> {
    return apiFetch<ConversationSession[]>("/conversations");
  },

  /**
   * POST /conversations
   * Creates a new conversation session.
   */
  async createConversation(title?: string): Promise<ConversationSession> {
    return apiFetch<ConversationSession>("/conversations", {
      method: "POST",
      body: JSON.stringify({ title: title || "New Conversation" }),
    });
  },

  /**
   * GET /conversations/{session_id}
   * Retrieves conversation metadata and messages.
   */
  async getConversation(sessionId: string): Promise<ConversationSession> {
    return apiFetch<ConversationSession>(`/conversations/${sessionId}`);
  },

  /**
   * GET /conversations/{session_id}/execution-status
   * Retrieves authoritative execution and HITL resolution status for the owned conversation.
   */
  async getExecutionStatus(sessionId: string): Promise<ConversationExecutionStatus> {
    return apiFetch<ConversationExecutionStatus>(`/conversations/${sessionId}/execution-status`);
  },

  /**
   * PATCH /conversations/{session_id}
   * Updates conversation title.
   */
  async updateConversation(sessionId: string, title: string): Promise<ConversationSession> {
    return apiFetch<ConversationSession>(`/conversations/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
  },

  /**
   * GET /conversations/{session_id}/messages
   * Retrieves stored messages array for the conversation.
   */
  async getMessages(sessionId: string): Promise<ConversationMessage[]> {
    return apiFetch<ConversationMessage[]>(`/conversations/${sessionId}/messages`);
  },

  /**
   * DELETE /conversations/{session_id}
   * Deletes a conversation session.
   */
  async deleteConversation(sessionId: string): Promise<{ status: string; id: string }> {
    return apiFetch<{ status: string; id: string }>(`/conversations/${sessionId}`, {
      method: "DELETE",
    });
  },

  /**
   * POST /chat
   * Submits user message query to sovereign agent, appending to specified session_id.
   */
  async sendMessage(message: string, sessionId?: string): Promise<ChatResponse> {
    return apiFetch<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
      timeoutMs: 120000,
    });
  },

  /**
   * POST /chat/stream
   * Submits user message query and streams live execution events over SSE.
   */
  async sendMessageStream(
    message: string,
    sessionId: string | undefined,
    onEvent: (event: ExecutionEvent) => void
  ): Promise<ChatResponse> {
    const url = `${env.apiUrl}/chat/stream`;
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    if (!response.ok) {
      let errText = `Request failed with status ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson.detail) errText = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      } catch {}
      throw new ApiError(errText, response.status);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new ApiError("Streaming response body is not readable", 500);
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult: ChatResponse | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.event) {
              onEvent(data.event);
            }
            if (data.result) {
              finalResult = data.result;
            }
            if (data.error) {
              throw new ApiError(data.error, 500);
            }
          } catch (e) {
            if (e instanceof ApiError) throw e;
            console.warn("Failed to parse SSE line:", trimmed, e);
          }
        }
      }
    }

    if (!finalResult) {
      throw new ApiError("Stream closed before receiving final execution result", 500);
    }
    return finalResult;
  },

  /**
   * POST /conversations/{session_id}/messages/{message_id}/edit
   * Submits an edited prompt for a previous message, preserving history and triggering a new agent execution.
   */
  async editPrompt(sessionId: string, messageId: string, message: string, model?: string): Promise<ChatResponse> {
    return apiFetch<ChatResponse>(`/conversations/${sessionId}/messages/${messageId}/edit`, {
      method: "POST",
      body: JSON.stringify({ message, model }),
      timeoutMs: 120000,
    });
  },

  /**
   * POST /conversations/{session_id}/messages/{message_id}/edit-stream
   * Submits an edited prompt and streams live execution events over SSE.
   */
  async editPromptStream(
    sessionId: string,
    messageId: string,
    message: string,
    model: string | undefined,
    onEvent: (event: ExecutionEvent) => void
  ): Promise<ChatResponse> {
    const url = `${env.apiUrl}/conversations/${sessionId}/messages/${messageId}/edit-stream`;
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ message, model }),
    });

    if (!response.ok) {
      let errText = `Request failed with status ${response.status}`;
      try {
        const errJson = await response.json();
        if (errJson.detail) errText = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      } catch {}
      throw new ApiError(errText, response.status);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new ApiError("Streaming response body is not readable", 500);
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult: ChatResponse | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6));
            if (data.event) {
              onEvent(data.event);
            }
            if (data.result) {
              finalResult = data.result;
            }
            if (data.error) {
              throw new ApiError(data.error, 500);
            }
          } catch (e) {
            if (e instanceof ApiError) throw e;
            console.warn("Failed to parse SSE line:", trimmed, e);
          }
        }
      }
    }

    if (!finalResult) {
      throw new ApiError("Stream closed before receiving final execution result", 500);
    }
    return finalResult;
  }
};

