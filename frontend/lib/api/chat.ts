import { apiFetch } from "./client";

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

export interface ChatResponse {
  success: boolean;
  session_id?: string;
  answer: string;
  sources: Array<{ filename: string; page_number: number; text?: string; distance?: number }>;
  verification: string;
  request_id: string;
  duration_ms: number;
  rag_used?: boolean;
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
  }
};
