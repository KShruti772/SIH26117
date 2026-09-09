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

export interface BlobDownloadResult {
  blob: Blob;
  filename: string;
  contentType: string | null;
  size: number;
}

/**
 * Robustly parses filename from HTTP Content-Disposition response header.
 * Supports standard filename="..." and RFC 5987 / RFC 6266 filename*=UTF-8''...
 */
export function extractFilenameFromHeader(header: string | null, fallback: string = "document.pdf"): string {
  if (!header || typeof header !== "string") return fallback;

  // 1. RFC 5987 / RFC 6266 extended UTF-8 filename (filename*=UTF-8''...)
  const utf8Match = header.match(/filename\*=(?:UTF-8''|utf-8'')?([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try {
      const clean = utf8Match[1].trim().replace(/^["']|["']$/g, "");
      return decodeURIComponent(clean);
    } catch {
      return utf8Match[1].trim().replace(/^["']|["']$/g, "");
    }
  }

  // 2. Standard filename parameter (filename="...")
  const standardMatch = header.match(/filename="?([^";]+)"?/i);
  if (standardMatch && standardMatch[1]) {
    return standardMatch[1].trim();
  }

  return fallback;
}

/**
 * Triggers a secure browser file download from an in-memory Blob and revokes object URL.
 */
export function triggerBrowserBlobDownload(blob: Blob, filename: string): void {
  if (typeof window === "undefined") return;
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl);
  }, 1000);
}

/**
 * Authenticated binary blob fetch wrapper.
 * Intercepts Bearer token, validates authorization status, and returns parsed Blob & metadata.
 */
export async function apiFetchBlob(
  path: string,
  options: RequestOptions = {},
  fallbackFilename: string = "download.pdf"
): Promise<BlobDownloadResult> {
  const { params, headers: customHeaders, timeoutMs, ...init } = options;

  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  let url = `${env.apiUrl}${cleanPath}`;
  if (params) {
    const searchParams = new URLSearchParams(params);
    url += `?${searchParams.toString()}`;
  }

  const headers = new Headers(customHeaders);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const method = (init.method || "GET").toUpperCase();
  if (process.env.NODE_ENV !== "production") {
    const maskedAuth = token ? `Bearer ${token.substring(0, 8)}...[TRUNCATED]` : "None";
    console.log(`[AEGIS BLOB REQUEST] ${method} ${url} (Auth: ${maskedAuth})`);
  }

  const controller = new AbortController();
  const requestTimeout = timeoutMs ?? 60000;
  const timeoutId = setTimeout(() => controller.abort(), requestTimeout);

  try {
    const response = await fetch(url, {
      ...init,
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (response.ok) {
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition");
      const filename = extractFilenameFromHeader(disposition, fallbackFilename);
      const contentType = response.headers.get("Content-Type");
      if (process.env.NODE_ENV !== "production") {
        console.log(`[AEGIS BLOB SUCCESS] ${method} ${url} -> HTTP ${response.status} (${blob.size} bytes, Filename: ${filename})`);
      }
      return {
        blob,
        filename,
        contentType,
        size: blob.size,
      };
    }

    let errMessage = `Download failed with status ${response.status}`;
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
      // Non-JSON response
    }

    if (process.env.NODE_ENV !== "production") {
      console.warn(`[AEGIS BLOB ERROR] ${method} ${url} -> HTTP ${response.status} | Detail: ${errMessage}`);
    }

    switch (response.status) {
      case 401:
        handleAuthExpiration();
        errMessage = "Session expired. Please sign in again.";
        break;
      case 403:
        errMessage = "Download not authorized for this document.";
        break;
      case 404:
        errMessage = "Document is no longer available.";
        break;
      default:
        errMessage = "Unable to download the document. Please retry.";
        break;
    }

    throw new ApiError(errMessage, response.status, detailObj);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    if (error instanceof Error && error.name === "AbortError") {
      const timeoutSec = Math.round(requestTimeout / 1000);
      throw new ApiError(`Download request timed out after ${timeoutSec} seconds. Please retry.`, 504, { targetUrl: url });
    }

    const failureReason = error instanceof Error ? error.message : String(error);
    throw new ApiError(
      `Unable to connect to the AEGIS backend for download. Details: ${failureReason}`,
      503,
      { networkReason: failureReason, targetUrl: url }
    );
  }
}

