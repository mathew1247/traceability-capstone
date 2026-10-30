/* ===================================================================
   SENTINEL-TRACE CENTRALIZED REST API CLIENT
   Secure JWT Bearer management, HTTP status handling, and clean JSON payloads
   =================================================================== */

const normalizeApiBase = (url) => {
  if (!url || typeof url !== 'string') return "";
  const trimmed = url.trim().replace(/\/+$/, '');
  return trimmed.endsWith('/api') ? trimmed : `${trimmed}/api`;
};

const getApiBaseUrl = () => {
  if (window.APP_CONFIG?.API_BASE_URL) return normalizeApiBase(window.APP_CONFIG.API_BASE_URL);
  const storedApi = localStorage.getItem("sentinel_api_base") || localStorage.getItem("API_BASE_URL");
  if (storedApi && !storedApi.includes("undefined") && !storedApi.includes("null")) {
    return normalizeApiBase(storedApi);
  }
  const hostname = window.location.hostname || '';
  if (hostname.endsWith('onrender.com')) {
    return `${window.location.origin}/api`;
  }
  const isLocalHost = hostname === 'localhost' || hostname === '127.0.0.1' || window.location.protocol === 'file:' || !hostname;
  return isLocalHost ? "http://127.0.0.1:5000/api" : "https://traceability-capstone.onrender.com/api";
};

const API_BASE_URL = getApiBaseUrl();

function getAuthToken() {
  return localStorage.getItem("token") || localStorage.getItem("sentinelToken") || sessionStorage.getItem("token") || sessionStorage.getItem("sentinelToken") || "";
}

function setAuthSession(token, user) {
  if (token) {
    localStorage.setItem("token", token);
    localStorage.setItem("sentinelToken", token);
    sessionStorage.setItem("token", token);
    sessionStorage.setItem("sentinelToken", token);
  }
  if (user) {
    let normalizedUser = user;
    if (typeof user === 'string') {
      try { normalizedUser = JSON.parse(user); } catch (e) { normalizedUser = { username: user }; }
    }
    if (normalizedUser && typeof normalizedUser === 'object') {
      const displayName = normalizedUser.username || normalizedUser.name || "Operator";
      const uId = normalizedUser.user_id || normalizedUser.id || "";
      normalizedUser.name = displayName;
      normalizedUser.username = displayName;
      normalizedUser.id = uId;
      normalizedUser.user_id = uId;
    }
    const userStr = JSON.stringify(normalizedUser);
    localStorage.setItem("user", userStr);
    localStorage.setItem("sentinelUser", userStr);
    sessionStorage.setItem("user", userStr);
    sessionStorage.setItem("sentinelUser", userStr);
  }
}

function clearAuthSession() {
  localStorage.removeItem("token");
  localStorage.removeItem("sentinelToken");
  localStorage.removeItem("user");
  localStorage.removeItem("sentinelUser");
  sessionStorage.removeItem("token");
  sessionStorage.removeItem("sentinelToken");
  sessionStorage.removeItem("user");
  sessionStorage.removeItem("sentinelUser");
}

async function request(endpoint, options = {}) {
  let url;
  if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) {
    url = endpoint;
  } else {
    const rawEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
    const cleanEndpoint = rawEndpoint.startsWith("/api/") ? rawEndpoint.substring(4) : (rawEndpoint === "/api" ? "" : rawEndpoint);
    url = `${API_BASE_URL}${cleanEndpoint}`;
  }
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
