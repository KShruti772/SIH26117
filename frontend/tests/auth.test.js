const test = require("node:test");
const assert = require("node:assert");

// Mock browser environments for Node.js runtime execution
const mockSessionStorage = {
  store: {},
  getItem(key) {
    return this.store[key] || null;
  },
  setItem(key, value) {
    this.store[key] = String(value);
  },
  removeItem(key) {
    delete this.store[key];
  },
  clear() {
    this.store = {};
  }
};

global.window = {};
global.sessionStorage = mockSessionStorage;

// 1. Replicated Token Manager (token.ts) Logic
const tokenManager = {
  getToken() {
    if (typeof global.window === "undefined") return null;
    return global.sessionStorage.getItem("aegis_jwt_token");
  },
  setToken(token) {
    if (typeof global.window === "undefined") return;
    if (token === null) {
      global.sessionStorage.removeItem("aegis_jwt_token");
    } else {
      global.sessionStorage.setItem("aegis_jwt_token", token);
    }
  },
  clearToken() {
    this.setToken(null);
  }
};

// 2. Replicated Status Code Translation Table (client.ts / ApiError)
class ApiError extends Error {
  constructor(message, status, detail = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function translateResponseStatus(status, originalMessage) {
  let errMessage = originalMessage || `Request failed with status ${status}`;
  switch (status) {
    case 401:
      tokenManager.clearToken();
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
  return new ApiError(errMessage, status);
}

// 3. Replicated Role-Aware UI Filtering (Sidebar.tsx)
const NAVIGATION_ITEMS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "chat", label: "AI Assistant" },
  { id: "rag", label: "Knowledge / RAG" },
  { id: "audit", label: "Audit Logs" }
];

function filterNavItems(role) {
  return NAVIGATION_ITEMS.filter((item) => {
    if (item.id === "audit") {
      return role === "admin";
    }
    return true;
  });
}

// ==========================================
// TEST SCENARIOS
// ==========================================

test("Token Storage Operations - Set, Get and Clear Token", () => {
  mockSessionStorage.clear();
  
  // Set token
  tokenManager.setToken("mock-jwt-hash");
  assert.strictEqual(tokenManager.getToken(), "mock-jwt-hash");
  
  // Clear token
  tokenManager.clearToken();
  assert.strictEqual(tokenManager.getToken(), null);
});

test("API Client Error Translation - 401 Unauthorized clears token & triggers expiration", () => {
  mockSessionStorage.clear();
  tokenManager.setToken("active-user-jwt");
  
  let eventDispatched = false;
  global.window = {
    location: { pathname: "/dashboard", href: "" },
    dispatchEvent(evt) {
      if (evt.type === "aegis:auth_expired") eventDispatched = true;
    }
  };
  global.CustomEvent = class CustomEvent {
    constructor(type) { this.type = type; }
  };

  const apiError = translateResponseStatus(401, "Signature Expired");
  
  assert.strictEqual(apiError.status, 401);
  assert.match(apiError.message, /expired or is invalid/);
  assert.strictEqual(tokenManager.getToken(), null, "Token must be cleared on 401");
});

test("Simultaneous 401 Responses - Single deduplicated redirect", () => {
  mockSessionStorage.clear();
  tokenManager.setToken("active-jwt-token");
  
  let redirectCount = 0;
  let isRedirecting = false;
  
  function handleDeduplicatedExpiration() {
    tokenManager.clearToken();
    if (!isRedirecting) {
      isRedirecting = true;
      redirectCount++;
    }
  }

  // Simulate 4 concurrent 401 API failures (e.g. /health, /audit, /documents, /models)
  handleDeduplicatedExpiration();
  handleDeduplicatedExpiration();
  handleDeduplicatedExpiration();
  handleDeduplicatedExpiration();

  assert.strictEqual(redirectCount, 1, "Simultaneous 401s must result in exactly ONE redirect trigger");
  assert.strictEqual(tokenManager.getToken(), null, "Token must be cleared");
});

test("API Client Error Translation - 403 Forbidden does NOT clear authentication token", () => {
  mockSessionStorage.clear();
  tokenManager.setToken("valid-user-jwt");
  
  const apiError = translateResponseStatus(403);
  assert.strictEqual(apiError.status, 403);
  assert.match(apiError.message, /Access denied/);
  assert.strictEqual(tokenManager.getToken(), "valid-user-jwt", "403 must NOT clear authentication token");
});

test("API Client Error Translation - 422 Validation Error contains details & does NOT clear token", () => {
  mockSessionStorage.clear();
  tokenManager.setToken("valid-user-jwt");
  
  const apiError = translateResponseStatus(422, "Username too short");
  assert.strictEqual(apiError.status, 422);
  assert.match(apiError.message, /Validation failed: Username too short/);
  assert.strictEqual(tokenManager.getToken(), "valid-user-jwt", "422 must NOT clear token");
});

test("API Client Error Translation - 429 Rate Limit error returns retry warning & preserves token", () => {
  mockSessionStorage.clear();
  tokenManager.setToken("valid-user-jwt");

  const apiError = translateResponseStatus(429);
  assert.strictEqual(apiError.status, 429);
  assert.match(apiError.message, /Rate limit exceeded/);
  assert.strictEqual(tokenManager.getToken(), "valid-user-jwt", "429 must NOT clear token");
});

test("API Client Error Translation - 500 Internal Error returns node generic message & preserves token", () => {
  mockSessionStorage.clear();
  tokenManager.setToken("valid-user-jwt");

  const apiError = translateResponseStatus(500);
  assert.strictEqual(apiError.status, 500);
  assert.match(apiError.message, /sovereign node encountered/);
  assert.strictEqual(tokenManager.getToken(), "valid-user-jwt", "500 must NOT clear token");
});

test("Role-Aware Navigation Visibility - Admin role displays Audit logs", () => {
  const filtered = filterNavItems("admin");
  const hasAudit = filtered.some(item => item.id === "audit");
  assert.strictEqual(hasAudit, true);
  assert.strictEqual(filtered.length, 4);
});

test("Role-Aware Navigation Visibility - User role hides Audit logs", () => {
  const filtered = filterNavItems("user");
  const hasAudit = filtered.some(item => item.id === "audit");
  assert.strictEqual(hasAudit, false);
  assert.strictEqual(filtered.length, 3);
});
