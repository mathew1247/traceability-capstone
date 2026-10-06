/* ===================================================================
   SENTINEL-TRACE CONFIGURATION & CENTRALIZED API SERVICE
   Real-Time Google Cloud Firestore Integration via Flask REST API
   =================================================================== */

// Global API Base Configuration - Production Safe Dynamic Host Resolution
const getProductionApiUrl = () => {
  if (window.APP_CONFIG?.API_BASE_URL) return window.APP_CONFIG.API_BASE_URL;
  if (window.API_BASE_URL) return window.API_BASE_URL;
  const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:' || !window.location.hostname;
  return isLocalHost ? "http://127.0.0.1:5000/api" : "https://traceability-capstone.onrender.com/api";
};

const API_BASE_URL = getProductionApiUrl();

// Helpers for Auth token & User state
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

// Universal API Request Dispatcher with Error, Status, and Auth Handling
async function apiRequest(endpoint, options = {}) {
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${API_BASE_URL}${cleanEndpoint}`;
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

    if (res.status === 401 && !cleanEndpoint.startsWith("/auth/login") && !cleanEndpoint.startsWith("/auth/register")) {
      console.warn(`[Sentinel API] Unauthorized access on ${endpoint}. Clearing session.`);
      clearAuthSession();
      if (!window.location.pathname.endsWith("login.html") && !window.location.pathname.endsWith("welcome.html")) {
        window.location.href = "login.html";
      }
      throw new Error("Authentication session expired. Please log in again.");
    }

    const json = await res.json().catch(() => null);

    if (!res.ok) {
      const errMsg = json?.error?.message || json?.message || `HTTP ${res.status}: Operation failed`;
      const err = new Error(errMsg);
      err.status = res.status;
      err.data = json;
      throw err;
    }

    // Return unpacked payload if wrapped in standard { success: true, data: ... }
    return json && json.data !== undefined ? json.data : json;
  } catch (err) {
    console.error(`[Sentinel API Error] ${url}:`, err.message);
    throw err;
  }
}

// 1. Auth Service
async function apiLogin(email, password) {
  const data = await apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });

  if (data && data.token) {
    setAuthSession(data.token, data.user);
    return { success: true, token: data.token, user: data.user };
  }
  return data;
}

async function apiRegister(username, email, password, role = "Operator") {
  const data = await apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, email, password, role })
  });
  return data;
}

// 2. Executive Dashboard Metrics (Calculated from Firestore)
async function getDashboardStats() {
  try {
    const stats = await apiRequest("/dashboard/stats");
    return {
      ...stats,
      totalBatches: stats.total_batches ?? 0,
      complianceRate: stats.compliance_rate !== undefined ? `${stats.compliance_rate}%` : "100%",
      networkStatus: stats.network_status || "Secure",
      activeAlerts: stats.active_alerts ?? stats.total_alerts ?? 0,
      devicesFound: stats.active_devices ?? 0,
      threatLevel: stats.threat_level || "Low"
    };
  } catch (err) {
    console.warn("Unable to load real dashboard stats:", err.message);
    return {
      totalBatches: 0,
      complianceRate: "0%",
      networkStatus: "Offline",
      activeAlerts: 0
    };
  }
}

// 3. Products
async function getProducts() {
  try {
    const list = await apiRequest("/products");
    return (list || []).map(p => ({
      ...p,
      id: p.product_id || p.id,
      name: p.product_name || p.name,
      code: p.product_code || p.code,
      compliance: p.compliance || "ISO 9001:2015",
      createdDate: p.created_at ? p.created_at.split("T")[0] : "2026-10-06"
    }));
  } catch (e) {
    console.error("Failed to fetch products:", e);
    return [];
  }
}

async function getProductById(id) {
  return await apiRequest(`/products/${id}`);
}

async function createProduct(product) {
  const payload = {
    product_name: product.product_name || product.name,
    product_code: product.product_code || product.code,
    description: product.description || product.compliance || "Precision industrial manufactured component",
    status: product.status || "In Production"
  };
  const created = await apiRequest("/products", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    ...created,
    id: created.product_id || created.id,
    name: created.product_name || created.name,
    code: created.product_code || created.code
  };
}

async function deleteProduct(id) {
  return await apiRequest(`/products/${id}`, { method: "DELETE" });
}

// 4. Production Batches
async function getBatches() {
  try {
    const list = await apiRequest("/batches");
    return (list || []).map(b => ({
      ...b,
      id: b.batch_id || b.id,
      product: b.product_name || b.product_id || b.product,
      material: b.material_name || b.material_id || b.material,
      quantity: b.quantity,
      date: b.production_date || (b.created_at ? b.created_at.split("T")[0] : "2026-10-06"),
      status: b.status || "Completed",
      operator: b.operator || "Jack Mathew"
    }));
  } catch (e) {
    console.error("Failed to fetch batches:", e);
    return [];
  }
}

async function getBatchById(id) {
  return await apiRequest(`/batches/${id}`);
}

async function createBatch(batch) {
  const payload = {
    product_id: batch.product_id || batch.product,
    material_id: batch.material_id || batch.material,
    quantity: parseInt(batch.quantity, 10),
    production_date: batch.production_date || batch.date || new Date().toISOString().split("T")[0],
    status: batch.status || "Running"
  };
  const created = await apiRequest("/batches", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    ...created,
    id: created.batch_id || created.id,
    product: created.product_id,
    material: created.material_id,
    date: created.production_date
  };
}

async function deleteBatch(id) {
  return await apiRequest(`/batches/${id}`, { method: "DELETE" });
}

// 5. Raw Materials
async function getMaterials() {
  try {
    const list = await apiRequest("/materials");
    return (list || []).map(m => ({
      ...m,
      id: m.material_id || m.id,
      name: m.material_name || m.name,
      supplier: m.supplier_name || m.supplier_id || m.supplier,
      quantity: m.quantity,
      unit: m.unit || "kg",
      status: m.status || "Verified",
      createdDate: m.created_at ? m.created_at.split("T")[0] : "2026-10-06"
    }));
  } catch (e) {
    console.error("Failed to fetch materials:", e);
    return [];
  }
}

async function getMaterialById(id) {
  return await apiRequest(`/materials/${id}`);
}

async function createMaterial(mat) {
  const payload = {
    material_name: mat.material_name || mat.name,
    supplier_id: mat.supplier_id || mat.supplier,
    quantity: parseFloat(mat.quantity),
    unit: mat.unit || "kg"
  };
  const created = await apiRequest("/materials", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    ...created,
    id: created.material_id || created.id,
    name: created.material_name || created.name,
    supplier: created.supplier_id
  };
}

async function deleteMaterial(id) {
  return await apiRequest(`/materials/${id}`, { method: "DELETE" });
}

// 6. Certified Industrial Suppliers
async function getSuppliers() {
  try {
    const list = await apiRequest("/suppliers");
    return (list || []).map(s => ({
      ...s,
      id: s.supplier_id || s.id,
      name: s.supplier_name || s.name,
      contact: s.contact,
      email: s.email,
      address: s.address,
      status: s.status || "Active",
      rating: s.rating || "4.8"
    }));
  } catch (e) {
    console.error("Failed to fetch suppliers:", e);
    return [];
  }
}

async function getSupplierById(id) {
  return await apiRequest(`/suppliers/${id}`);
}

async function createSupplier(sup) {
  const payload = {
    supplier_name: sup.supplier_name || sup.name,
    contact: sup.contact,
    email: sup.email,
    address: sup.address,
    status: sup.status || "Active"
  };
  const created = await apiRequest("/suppliers", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    ...created,
    id: created.supplier_id || created.id,
    name: created.supplier_name || created.name
  };
}

async function deleteSupplier(id) {
  return await apiRequest(`/suppliers/${id}`, { method: "DELETE" });
}

// 7. Compliance Records
async function getCompliance() {
  try {
    const list = await apiRequest("/compliance");
    return (list || []).map(c => ({
      ...c,
      id: c.compliance_id || c.id,
      product: c.product_id || c.product,
      standard: c.standard,
      status: c.status,
      auditor: c.audited_by || c.auditor || "Authorized Auditor",
      expiryDate: c.expiry_date || c.expiryDate,
      score: c.score || "98.5%"
    }));
  } catch (e) {
    console.error("Failed to fetch compliance records:", e);
    return [];
  }
}

async function createCompliance(comp) {
  const payload = {
    product_id: comp.product_id || comp.product,
    standard: comp.standard,
    status: comp.status || "Compliant",
    audited_by: comp.audited_by || comp.auditor || "USR-ADMIN01",
    expiry_date: comp.expiry_date || comp.expiryDate,
    remarks: comp.remarks || "Compliance audit verified against specifications."
  };
  const created = await apiRequest("/compliance", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    ...created,
    id: created.compliance_id || created.id,
    product: created.product_id,
    expiryDate: created.expiry_date
  };
}

async function deleteCompliance(id) {
  return await apiRequest(`/compliance/${id}`, { method: "DELETE" });
}

// 8. Traceability Lineage Graph
async function getTraceability(id) {
  return await apiRequest(`/traceability/${id}`);
}

// 9. Network Scanner (Flask -> Authorized Nmap execution -> Firestore)
function normalizeScanObject(s) {
  if (!s) return null;
  return {
    ...s,
    id: s.scan_id || s.id,
    target: s.target,
    duration: s.duration || "1.42s",
    devicesFound: s.devices_found ?? s.devicesFound ?? 0,
    status: s.status || "Completed",
    timestamp: s.scan_date ? s.scan_date.replace("T", " ").substring(0, 19) : (s.timestamp || "Recent"),
    openPorts: (s.open_ports || s.openPorts || []).map(p => ({
      port: p.port,
      service: p.service,
      host: p.host,
      state: p.state || "open",
      risk: p.is_critical ? "Critical" : (p.risk || "Normal")
    }))
  };
}

async function startNetworkScan(target = "192.168.1.0/24") {
  const res = await apiRequest("/network/scan", {
    method: "POST",
    body: JSON.stringify({ target })
  });
  return normalizeScanObject(res);
}

async function getNetworkHistory() {
  try {
    const scans = await apiRequest("/network/history");
    return (scans || []).map(normalizeScanObject);
  } catch (e) {
    console.error("Failed to fetch network scans:", e);
    return [];
  }
}

async function getNetworkSecurity() {
  try {
    const sec = await apiRequest("/network/security");
    return sec || {};
  } catch (e) {
    console.error("Failed to fetch network security summary:", e);
    return {};
  }
}

// 10. Operational & Security Alerts
async function getAlerts(filters = {}) {
  try {
    let query = "";
    if (filters.status) query += `?status=${filters.status}`;
    if (filters.severity) query += `${query ? '&' : '?'}severity=${filters.severity}`;
    const list = await apiRequest(`/alerts${query}`);
    return (list || []).map(a => ({
      ...a,
      id: a.alert_id || a.id,
      severity: a.severity || "Warning",
      title: a.message || a.title || "Operational Alert",
      details: a.message || a.details,
      status: a.status || "Active",
      timestamp: a.created_at ? a.created_at.split("T")[0] : "Recent"
    }));
  } catch (e) {
    console.error("Failed to fetch alerts:", e);
    return [];
  }
}

async function updateAlert(id, action) {
  return await apiRequest(`/alerts/${id}`, {
    method: "PUT",
    body: JSON.stringify({ action: action.toLowerCase() })
  });
}

// 11. Immutable Activity & Audit Logs
async function getActivityLogs() {
  try {
    const logs = await apiRequest("/logs");
    return (list = logs || []).map(l => ({
      ...l,
      id: l.log_id || l.id,
      timestamp: l.timestamp ? l.timestamp.replace("T", " ").substring(0, 19) : "2026-10-06 12:00:00",
      user: l.username || l.user_id || "System",
      role: l.role || "Operator",
      action: l.action,
      resource: l.resource,
      ip: l.ip_address || "127.0.0.1",
      status: "Success"
    }));
  } catch (e) {
    console.error("Failed to fetch activity logs:", e);
    return [];
  }
}

// 12. User Management (Admin Only)
async function getUsers() {
  try {
    const users = await apiRequest("/admin/users");
    return (users || []).map(u => ({
      ...u,
      id: u.user_id || u.id,
      name: u.username || u.name,
      email: u.email,
      role: u.role,
      status: u.status || "Active",
      createdDate: u.created_at ? u.created_at.split("T")[0] : "2026-10-06"
    }));
  } catch (e) {
    console.error("Failed to fetch users:", e);
    return [];
  }
}

async function createUser(user) {
  const payload = {
    username: user.username || user.name,
    email: user.email,
    password: user.password || "ChangeMe123!",
    role: user.role || "Operator",
    status: user.status || "Active"
  };
  const created = await apiRequest("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    ...created,
    id: created.user_id || created.id,
    name: created.username || created.name
  };
}

async function toggleUserStatus(id) {
  const users = await getUsers();
  const current = users.find(u => u.id === id);
  const nextStatus = current && current.status === "Active" ? "Inactive" : "Active";

  return await apiRequest(`/admin/users/${id}/status`, {
    method: "PUT",
    body: JSON.stringify({ status: nextStatus })
  });
}

// 13. Reports & Analytics Summary
async function getReportsSummary() {
  try {
    return await apiRequest("/reports/summary");
  } catch (e) {
    console.error("Failed to fetch reports summary:", e);
    return null;
  }
}

// Export everything to window
window.API_BASE_URL = API_BASE_URL;
window.apiRequest = apiRequest;
window.apiLogin = apiLogin;
window.apiRegister = apiRegister;
window.getDashboardStats = getDashboardStats;
window.getProducts = getProducts;
window.getProductById = getProductById;
window.createProduct = createProduct;
window.deleteProduct = deleteProduct;
window.getBatches = getBatches;
window.getBatchById = getBatchById;
window.createBatch = createBatch;
window.deleteBatch = deleteBatch;
window.getMaterials = getMaterials;
window.getMaterialById = getMaterialById;
window.createMaterial = createMaterial;
window.deleteMaterial = deleteMaterial;
window.getSuppliers = getSuppliers;
window.getSupplierById = getSupplierById;
window.createSupplier = createSupplier;
window.deleteSupplier = deleteSupplier;
window.getCompliance = getCompliance;
window.createCompliance = createCompliance;
window.deleteCompliance = deleteCompliance;
window.getTraceability = getTraceability;
window.startNetworkScan = startNetworkScan;
window.getNetworkHistory = getNetworkHistory;
window.getNetworkSecurity = getNetworkSecurity;
window.getAlerts = getAlerts;
window.updateAlert = updateAlert;
window.getActivityLogs = getActivityLogs;
window.getUsers = getUsers;
window.createUser = createUser;
window.toggleUserStatus = toggleUserStatus;
window.getReportsSummary = getReportsSummary;
