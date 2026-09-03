import { env } from "../config/env";
import { getToken, clearToken } from "../security/token";

export class ApiError extends Error {
  status: number;
  detail: any;

  constructor(message: string, status: number, detail: any = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string>;
  timeoutMs?: number;
}

let isRedirectingToLogin = false;

export function handleAuthExpiration(): void {
  clearToken();
  if (typeof window !== "undefined") {
    // Notify AuthProvider to scrub in-memory user state
    window.dispatchEvent(new CustomEvent("aegis:auth_expired"));

    // Prevent duplicate redirects when multiple API requests receive 401 simultaneously
    if (!isRedirectingToLogin && !window.location.pathname.startsWith("/login")) {
      isRedirectingToLogin = true;
      setTimeout(() => {
        isRedirectingToLogin = false;
      }, 3000);
      window.location.href = "/login?expired=true";
    }
  }
}

/**
 * Core HTTP Request wrapper with JWT interception and status translation
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers: customHeaders, body, timeoutMs, ...init } = options;

  // 1. Build URL with query params if provided
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  let url = `${env.apiUrl}${cleanPath}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  // 2. Set defaults headers
  const headers = new Headers(customHeaders);
  
  // Attach JWT bearer token if exists
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Automatically content-type to JSON unless sending multipart/FormData
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // Development console diagnostics
  const method = (init.method || "GET").toUpperCase();
  if (process.env.NODE_ENV !== "production") {
    const maskedAuth = token ? `Bearer ${token.substring(0, 8)}...[TRUNCATED]` : "None";
    console.log(`[AEGIS API REQUEST] ${method} ${url} (Auth: ${maskedAuth})`);
  }

  // 3. Set request timeout via AbortController (default 60s for local inference/embeddings)
  const controller = new AbortController();
  const requestTimeout = timeoutMs ?? 60000;
  const timeoutId = setTimeout(() => controller.abort(), requestTimeout);

  try {
    const response = await fetch(url, {
      ...init,
      body,
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    // 3. Handle success responses
    if (response.ok) {
      if (process.env.NODE_ENV !== "production") {
        console.log(`[AEGIS API SUCCESS] ${method} ${url} -> HTTP ${response.status}`);
      }
      if (response.status === 204) {
        return null as unknown as T;
      }
      return await response.json() as T;
    }

    // 4. Handle error responses (parse API detail objects safely)
    let errMessage = `Request failed with status ${response.status}`;
    let detailObj: any = null;

    try {
      const data = await response.json();
      detailObj = data.detail;
      if (typeof data.detail === "string") {
        errMessage = data.detail;
      } else if (data.detail && typeof data.detail === "object") {
        errMessage = JSON.stringify(data.detail);
      }
    } catch {
      // Response was not JSON
    }

    if (process.env.NODE_ENV !== "production") {
      console.warn(`[AEGIS API ERROR] ${method} ${url} -> HTTP ${response.status} (${response.statusText}) | Detail: ${errMessage}`);
    }

    // 5. Clean translation of standard HTTP status codes
    switch (response.status) {
      case 401:
        handleAuthExpiration();
        errMessage = "Token signature has expired or is invalid. Please log in again.";
        break;
      case 403:
        errMessage = "Access denied. You do not have the required permissions for this action.";
        break;
      case 404:
        errMessage = "The requested resource could not be found on the server.";
        break;
      case 422:
        errMessage = `Validation failed: ${errMessage || "Invalid request fields format."}`;
        break;
      case 429:
        errMessage = "Rate limit exceeded. Please wait before submitting more requests.";
        break;
      case 500:
        errMessage = "Internal server error. The sovereign node encountered an unexpected fault.";
        break;
      default:
        break;
    }

    throw new ApiError(errMessage, response.status, detailObj);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    
    // Check if error was caused by AbortController timeout
    if (error instanceof Error && error.name === "AbortError") {
      const timeoutSec = Math.round(requestTimeout / 1000);
      const timeoutMsg = `Request timed out after ${timeoutSec} seconds while waiting for the AEGIS local backend.`;
      if (process.env.NODE_ENV !== "production") {
        console.error(`[AEGIS API TIMEOUT] ${method} ${url} exceeded timeout of ${timeoutSec}s`);
      }
      throw new ApiError(timeoutMsg, 504, { timedOut: true, timeoutSec, targetUrl: url });
    }

    const failureReason = error instanceof Error ? error.message : String(error);
    if (process.env.NODE_ENV !== "production") {
      console.error(`[AEGIS API NETWORK FAILURE] ${method} ${url} failed to reach server. Reason: ${failureReason}`);
    }
    // Convert network connection failures into clean error with details
    throw new ApiError(
      `Unable to connect to the AEGIS backend at ${env.apiUrl}. Details: ${failureReason}`,
      503,
      { networkReason: failureReason, targetUrl: url }
    );
  }
}
