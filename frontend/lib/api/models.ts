import { apiFetch } from "./client";

export interface ModelProfile {
  model_id: string;
  display_name: string;
  runtime_model_name: string;
  provider: string;
  runtime: string;
  capabilities: string[];
  status: string;
  is_installed?: boolean;
  is_active?: boolean;
  size_bytes?: number;
  modified_at?: string;
  parameter_size?: string;
  quantization?: string;
  estimated_vram_gb?: number;
  format?: string;
  family?: string;
  notes?: string;
}

export interface ModelLoaderStatus {
  status: "success" | "failure";
  model_id: string;
  active_model: string;
  details?: string;
  warning?: string;
}

export interface ModelTestResult {
  status: "PASS" | "FAIL";
  model: string;
  latency_ms: number | null;
  response?: string;
  error?: string;
}

export const modelsApi = {
  /**
   * Retrieves all discovered local AI models and their metadata profiles.
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
   * Initiates dynamic model switch sequence.
   */
  async switchModel(modelId: string): Promise<ModelLoaderStatus> {
    return apiFetch<ModelLoaderStatus>("/models/select", {
      method: "POST",
      body: JSON.stringify({ model_id: modelId })
    });
  },

  /**
   * Executes deterministic test inference against target local model.
   */
  async testInference(modelId?: string): Promise<ModelTestResult> {
    return apiFetch<ModelTestResult>("/models/test", {
      method: "POST",
      body: JSON.stringify({ model_id: modelId })
    });
  }
};
