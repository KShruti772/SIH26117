import { apiFetch } from "./client";
import { setToken, clearToken } from "../security/token";

export interface User {
  id: number;
  username: string;
  role: "admin" | "user";
  department_id?: number;
  department_name?: string;
  is_active: boolean;
  must_change_password?: boolean;
  created_at: string;
}

export interface Department {
  id: number;
  name: string;
  code: string;
  description?: string;
  is_active: boolean;
  user_count?: number;
  created_at?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface UserRegisterPayload {
  username: string;
  password: string;
  department_id?: number;
}

export interface UserLoginPayload {
  username: string;
  password: string;
}

/**
 * Discovered Backend API: Authentication Services & Department Management
 */
export const authApi = {
  /**
   * POST /auth/register
   * Registers a new user with department assignment.
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
   * GET /departments
   * Retrieves list of all organizational departments.
   */
  async listDepartments(): Promise<Department[]> {
    return apiFetch<Department[]>("/departments", {
      method: "GET",
    });
  },

  /**
   * POST /departments
   * Creates a new organizational department (Admin only).
   */
  async createDepartment(payload: { name: string; code: string; description?: string }): Promise<Department> {
    return apiFetch<Department>("/departments", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * PATCH /departments/:id
   * Updates department details or active status (Admin only).
   */
  async updateDepartment(id: number, payload: { name?: string; description?: string; is_active?: boolean }): Promise<Department> {
    return apiFetch<Department>(`/departments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  /**
   * PATCH /users/:username/department
   * Assigns or updates a user's department (Admin only).
   */
  async updateUserDepartment(username: string, departmentId: number): Promise<User> {
    return apiFetch<User>(`/users/${encodeURIComponent(username)}/department`, {
      method: "PATCH",
      body: JSON.stringify({ department_id: departmentId }),
    });
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
