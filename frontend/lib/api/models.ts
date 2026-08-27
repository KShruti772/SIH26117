/**
 * Dynamic Model Loader API Stubs
 * 
 * DESIGN NOTICE:
 * These stubs represent client-side interfaces that will map to future backend endpoints.
 * The underlying loader manager handles dynamic swapping and VRAM allocations, and will 
 * be exposed via API routers in a future task.
 */

export interface ModelProfile {
  model_id: string;
  name: string;
  runtime: string;
  runtime_model_name: string;
  type: string;
  description: string;
  requirements: {
    vram_gb: number;
    ram_gb: number;
  };
  capabilities: string[];
}

export interface ModelLoaderStatus {
  status: "success" | "failure";
  model_id: string;
  active_model: string;
  details?: string;
}

export const modelsApi = {
  /**
   * Future GET /api/models/registry
   * Retrieves all registered local AI models and their metadata profiles.
   */
  async listRegistry(): Promise<ModelProfile[]> {
    console.warn("Models API: listRegistry stub invoked.");
    return [];
  },

  /**
   * Future GET /api/models/running
   * Lists currently loaded inference models in VRAM.
   */
  async getRunning(): Promise<string[]> {
    console.warn("Models API: getRunning stub invoked.");
    return [];
  },

  /**
   * Future POST /api/models/switch
   * Initiates dynamic VRAM model load/unload sequence.
   */
  async switchModel(modelId: string): Promise<ModelLoaderStatus> {
    console.warn("Models API: switchModel stub invoked.", modelId);
    return { status: "success", model_id: modelId, active_model: modelId };
  }
};
