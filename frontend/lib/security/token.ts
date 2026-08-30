/**
 * AEGIS Frontend Token Storage Strategy
 * 
 * SECURITY BOUNDARY DESIGN NOTICE:
 * 1. For this hackathon MVP, the JWT token is stored inside standard browser `sessionStorage` 
 *    (which isolates the token to the active browser tab session, reducing exposure compared to localStorage).
 * 2. PRODUCTION UPGRADE REQUIREMENT: To achieve industrial confidentiality controls and prevent 
 *    Cross-Site Scripting (XSS) tokens theft, the authentication flow should use HttpOnly, Secure, 
 *    SameSite=Strict cookies. This prevents JavaScript from accessing token hashes entirely.
 * 3. By centralizing get/set operations in this module, we can transition the client to 
 *    cookies or memory-based refresh token loops without modifying any api/ client logic.
 */

const TOKEN_KEY = "aegis_jwt_token";
const LEGACY_TOKEN_KEY = "auth_token";
const USER_KEYS = ["auth_user", "aegis_user"];

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return (
    sessionStorage.getItem(TOKEN_KEY) ||
    sessionStorage.getItem(LEGACY_TOKEN_KEY) ||
    localStorage.getItem(LEGACY_TOKEN_KEY) ||
    localStorage.getItem(TOKEN_KEY)
  );
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token === null) {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(LEGACY_TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(LEGACY_TOKEN_KEY);
    USER_KEYS.forEach((key) => {
      sessionStorage.removeItem(key);
      localStorage.removeItem(key);
    });
  } else {
    sessionStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(LEGACY_TOKEN_KEY, token);
  }
}

export function clearToken(): void {
  setToken(null);
}
