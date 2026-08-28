import { apiFetch } from "./client";

export interface ModelProfile {
  model_id: string;
  display_name: string;
  runtime_model_name: string;
  provider: string;
  runtime: string;
  capabilities: string[];
  model_type: string;
  context_length: number;
  quantization: string;
  estimated_vram_gb: number;
  estimated_ram_gb: number;
  priority: number;
  enabled: boolean;
  requires_gpu: boolean;
  supports_cpu: boolean;
  supports_vision: boolean;
  supports_code: boolean;
  supports_text: boolean;
  status: string;
}

export interface ModelLoaderStatus {
  status: "success" | "failure";
  model_id: string;
  active_model: string;
  details?: string;
  warning?: string;
}

export const modelsApi = {
  /**
   * Retrieves all registered local AI models and their metadata profiles.
   */
  async listRegistry(): Promise<ModelProfile[]> {
    return apiFetch<ModelProfile[]>("/models");
  },

  /**
   * Retrieves the currently selected/active model profile.
   */
  async getCurrentModel(): Promise<ModelProfile> {
    return apiFetch<ModelProfile>("/models/current");
  },

  /**
   * Initiates dynamic VRAM model load/unload sequence.
   */
  async switchModel(modelId: string): Promise<ModelLoaderStatus> {
    return apiFetch<ModelLoaderStatus>("/models/select", {
      method: "POST",
      body: JSON.stringify({ model_id: modelId })
    });
  }
};
