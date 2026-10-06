/* ===================================================================
   SENTINEL-TRACE CENTRALIZED REST API CLIENT
   Secure JWT Bearer management, HTTP status handling, and clean JSON payloads
   =================================================================== */

const API_BASE_URL = window.APP_CONFIG?.API_BASE_URL || window.API_BASE_URL || "http://127.0.0.1:5000";

function getAuthToken() {
  return localStorage.getItem("token") || localStorage.getItem("sentinelToken") || "";
}

function setAuthSession(token, user) {
  if (token) {
    localStorage.setItem("token", token);
    localStorage.setItem("sentinelToken", token);
  }
  if (user) {
    localStorage.setItem("user", JSON.stringify(user));
    localStorage.setItem("sentinelUser", JSON.stringify(user));
  }
}

function clearAuthSession() {
  localStorage.removeItem("token");
  localStorage.removeItem("sentinelToken");
  localStorage.removeItem("user");
  localStorage.removeItem("sentinelUser");
}

async function request(endpoint, options = {}) {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;
  const token = getAuthToken();

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers
    });

    if (res.status === 401) {
      console.warn("Unauthorized / Token expired. Redirecting to login...");
      clearAuthSession();
      if (!window.location.pathname.endsWith("login.html") && !window.location.pathname.endsWith("welcome.html")) {
        window.location.href = "login.html";
      }
      throw new Error("Session expired. Please log in again.");
    }

    const json = await res.json().catch(() => null);

    if (!res.ok) {
      const errMsg = json?.error?.message || json?.message || `HTTP ${res.status}: Request failed`;
      const err = new Error(errMsg);
      err.status = res.status;
      err.data = json;
      throw err;
    }

    return json;
  } catch (err) {
    if (err.name === "TypeError" && err.message.includes("fetch")) {
      console.error(`Network error connecting to Flask backend at ${url}:`, err);
      throw new Error(`Unable to connect to Sentinel-Trace server (${url}). Ensure backend is running.`);
    }
    throw err;
  }
}

async function apiGet(endpoint) {
  return request(endpoint, { method: "GET" });
}

async function apiPost(endpoint, body = {}) {
  return request(endpoint, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

async function apiPut(endpoint, body = {}) {
  return request(endpoint, {
    method: "PUT",
    body: JSON.stringify(body)
  });
}

async function apiDelete(endpoint) {
  return request(endpoint, { method: "DELETE" });
}

// Expose globally
window.API_BASE_URL = API_BASE_URL;
window.getAuthToken = getAuthToken;
window.setAuthSession = setAuthSession;
window.clearAuthSession = clearAuthSession;
window.apiGet = apiGet;
window.apiPost = apiPost;
window.apiPut = apiPut;
window.apiDelete = apiDelete;
