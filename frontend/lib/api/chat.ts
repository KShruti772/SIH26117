import { apiFetch } from "./client";

export interface ChatResponse {
  success: boolean;
  session_id?: string;
  answer: string;
  sources: Array<{ filename: string; page_number: number; text?: string; distance?: number }>;
  verification: string;
  request_id: string;
  duration_ms: number;
  rag_used?: boolean;
  model_info?: {
    model_id: string;
    inference_mode: string;
  };
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
}

export interface ConversationSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
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
    });
  }
};
