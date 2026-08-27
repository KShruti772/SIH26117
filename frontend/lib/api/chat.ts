import { apiFetch } from "./client";

export interface ChatResponse {
  success: boolean;
  answer: string;
  sources: Array<{ filename: string; page_number: number }>;
  verification: string;
  request_id: string;
  duration_ms: number;
}

/**
 * Discovered Backend API: Agent Operations / Chat Services
 */
export const chatApi = {
  /**
   * POST /chat
   * Submits user message query request to the multi-step sovereign agent planning pipeline.
   */
  async sendMessage(message: string): Promise<ChatResponse> {
    return apiFetch<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  }
};
