import { apiFetch } from "./client";
import { setToken, clearToken } from "../security/token";

export interface User {
  id: number;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
  must_change_password?: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface UserRegisterPayload {
  username: string;
  password: string;
}

export interface UserLoginPayload {
  username: string;
  password: string;
}

/**
 * Discovered Backend API: Authentication Services
 */
export const authApi = {
  /**
   * POST /auth/register
   * Registers a new user. Default role is 'user', admins require 'admin' in username.
   */
  async register(payload: UserRegisterPayload): Promise<User> {
    return apiFetch<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * POST /auth/login
   * Authenticates username and password credentials. Sets the active JWT token.
   */
  async login(payload: UserLoginPayload): Promise<TokenResponse> {
    const data = await apiFetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setToken(data.access_token);
    return data;
  },

  /**
   * GET /auth/me
   * Retrieves profile details for the currently active session.
   */
  async getProfile(): Promise<User> {
    return apiFetch<User>("/auth/me");
  },

  /**
   * Safely clears JWT tokens and terminates active browser tab sessions.
   */
  async logout(): Promise<void> {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Fail-safe: proceed to clear local token even if network fails
    } finally {
      clearToken();
    }
  }
};
