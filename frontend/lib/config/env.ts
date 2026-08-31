/**
 * Safe Browser-Exposed Configuration Settings
 */
export const env = {
  apiUrl: (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, ""),
};
