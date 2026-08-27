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
}

/**
 * Core HTTP Request wrapper with JWT interception and status translation
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { params, headers: customHeaders, body, ...init } = options;

  // 1. Build URL with query params if provided
  let url = `${env.apiUrl}${path}`;
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

  try {
    const response = await fetch(url, {
      ...init,
      body,
      headers,
    });

    // 3. Handle success responses
    if (response.ok) {
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

    // 5. Clean translation of standard HTTP status codes
    switch (response.status) {
      case 401:
        clearToken();
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
    // Convert network timeout/connection failures into safe text
    throw new ApiError("Local area network service is currently unreachable.", 503);
  }
}
