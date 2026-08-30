import { apiFetch } from "./client";

export interface UserProfile {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export const usersApi = {
  /**
   * GET /auth/users
   * Retrieves all registered users. Restricted to admin role.
   */
  async listUsers(): Promise<UserProfile[]> {
    return apiFetch<UserProfile[]>("/auth/users", {
      method: "GET",
    });
  },

  /**
   * POST /auth/users
   * Provisions a new user account with initial temporary credentials.
   */
  async provisionUser(payload: Record<string, string>): Promise<UserProfile> {
    return apiFetch<UserProfile>("/auth/users", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * POST /auth/users/{username}/status
   * Enables or disables target user account.
   */
  async updateUserStatus(username: string, is_active: boolean): Promise<UserProfile> {
    return apiFetch<UserProfile>(`/auth/users/${username}/status`, {
      method: "POST",
      body: JSON.stringify({ is_active }),
    });
  },

  /**
   * POST /auth/users/{username}/role
   * Updates target user role assignment.
   */
  async updateUserRole(username: string, role: string): Promise<UserProfile> {
    return apiFetch<UserProfile>(`/auth/users/${username}/role`, {
      method: "POST",
      body: JSON.stringify({ role }),
    });
  },

  /**
   * POST /auth/users/{username}/reset-password
   * Resets password and forces change password flag.
   */
  async resetPassword(username: string, password: string): Promise<UserProfile> {
    return apiFetch<UserProfile>(`/auth/users/${username}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    });
  },

  /**
   * POST /auth/change-password
   * Allows logged-in user to change password and clears must_change_password flag.
   */
  async changePassword(payload: Record<string, string>): Promise<{ status: string; message: string }> {
    return apiFetch<{ status: string; message: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
};
