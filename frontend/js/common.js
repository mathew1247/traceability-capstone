/* ===================================================================
   SENTINEL-TRACE COMMON COMPONENT INJECTION & SHELL CONTROLLER
   Injects Sidebar, Header, Handles Auth Guards, Toasts, Modals, Responsive Drawer
   =================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  initAuthGuard();
  injectSidebar();
  injectHeader();
  injectDock();
  initToastContainer();
  initShortcutListeners();
});

// Current User State
function getCurrentUser() {
  try {
    const raw = localStorage.getItem("sentinelUser");
    if (raw) return JSON.parse(raw);
  } catch (e) {}
  return {
    id: "USR-001",
    name: "Jack Mathew",
    email: "jack@sentineltrace.io",
    role: "Admin",
    status: "Active"
  };
}

// Auth Guard for Protected Pages
function initAuthGuard() {
  const path = window.location.pathname;
  const isAuthPage = path.endsWith("login.html") || path.endsWith("register.html") || path.endsWith("welcome.html");
  const token = localStorage.getItem("token") || localStorage.getItem("sentinelToken");

  if (!isAuthPage && !token) {
    window.location.href = "welcome.html";
    return;
  }

  // Admin Route Guard
  if (path.endsWith("users.html")) {
    const user = getCurrentUser();
    if (user.role !== "Admin") {
      alert("Access Denied: Administration section requires Administrator credentials.");
      window.location.href = "dashboard.html";
    }
  }
}

// Sidebar is disabled (All sections migrated to Floating Top Navigation Bar)
function injectSidebar() {
  const mount = document.getElementById("sidebar-mount");
  if (mount) {
    mount.innerHTML = "";
    mount.style.display = "none";
  }
}

// Injects the Categorized Floating Center Header Navbar (No Sidebar Needed)
function injectHeader() {
  const mount = document.getElementById("header-mount");
  if (!mount) return;

  const path = window.location.pathname;
  const user = getCurrentUser();

  const isDash = path.endsWith("dashboard.html") || path.endsWith("/");
  const isTraceCat = path.endsWith("traceability.html") || path.endsWith("products.html") || path.endsWith("batches.html") || path.endsWith("materials.html") || path.endsWith("suppliers.html");
  const isComp = path.endsWith("compliance.html");
  const isNetCat = path.endsWith("network-scan.html") || path.endsWith("network-security.html");
  const isMonCat = path.endsWith("alerts.html") || path.endsWith("reports.html") || path.endsWith("activity-logs.html");
  const isAdminCat = path.endsWith("users.html");

  mount.innerHTML = `
    <header class="app-header">
      <div style="display: flex; align-items: center; gap: 14px;">
        <!-- Brand Logo Pill (Left Side) -->
        <a href="dashboard.html" class="header-brand-logo" title="Sentinel-Trace Intelligence">
          <div class="header-brand-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              <path d="m9 12 2 2 4-4"/>
            </svg>
          </div>
          <div class="header-brand-text">
            <span class="header-brand-title">SENTINEL-TRACE</span>
            <span class="header-brand-subtitle">INDUSTRIAL INTELLIGENCE</span>
          </div>
        </a>

        <!-- Categorized Floating Center Navigation Bar -->
        <nav class="header-pill-nav">
          <!-- 1. Overview -->
          <a href="dashboard.html" class="header-pill-link ${isDash ? 'active' : ''}">
            ${getIconSvg('layout-dashboard')}
            <span>Overview</span>
          </a>

          <!-- 2. Traceability Category Dropdown -->
          <div class="header-pill-dropdown-wrapper">
            <button class="header-pill-link ${isTraceCat ? 'active' : ''}">
              ${getIconSvg('git-fork')}
              <span>Traceability</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="header-pill-dropdown-menu">
              <a href="traceability.html" class="dropdown-item ${path.endsWith('traceability.html') ? 'active' : ''}">
                ${getIconSvg('git-fork')}
                <span>Traceability Graph</span>
              </a>
              <a href="products.html" class="dropdown-item ${path.endsWith('products.html') ? 'active' : ''}">
                ${getIconSvg('box')}
                <span>Products</span>
              </a>
              <a href="batches.html" class="dropdown-item ${path.endsWith('batches.html') ? 'active' : ''}">
                ${getIconSvg('layers')}
                <span>Production Batches</span>
              </a>
              <a href="materials.html" class="dropdown-item ${path.endsWith('materials.html') ? 'active' : ''}">
                ${getIconSvg('cubes')}
                <span>Raw Materials</span>
              </a>
              <a href="suppliers.html" class="dropdown-item ${path.endsWith('suppliers.html') ? 'active' : ''}">
                ${getIconSvg('truck')}
                <span>Suppliers Directory</span>
              </a>
            </div>
          </div>

          <!-- 3. Compliance -->
          <a href="compliance.html" class="header-pill-link ${isComp ? 'active' : ''}">
            ${getIconSvg('shield-check')}
            <span>Compliance</span>
          </a>

          <!-- 4. Network Security Category Dropdown -->
          <div class="header-pill-dropdown-wrapper">
            <button class="header-pill-link ${isNetCat ? 'active' : ''}">
              ${getIconSvg('radar')}
              <span>Network Security</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="header-pill-dropdown-menu">
              <a href="network-scan.html" class="dropdown-item ${path.endsWith('network-scan.html') ? 'active' : ''}">
                ${getIconSvg('radar')}
                <span>Network Subnet Scanner</span>
              </a>
              <a href="network-security.html" class="dropdown-item ${path.endsWith('network-security.html') ? 'active' : ''}">
                ${getIconSvg('shield-alert')}
                <span>Security Monitor SOC</span>
              </a>
            </div>
          </div>

          <!-- 5. Monitoring Category Dropdown -->
          <div class="header-pill-dropdown-wrapper">
            <button class="header-pill-link ${isMonCat ? 'active' : ''}">
              ${getIconSvg('bell-ring')}
              <span>Monitoring</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="header-pill-dropdown-menu">
              <a href="alerts.html" class="dropdown-item ${path.endsWith('alerts.html') ? 'active' : ''}">
                ${getIconSvg('bell-ring')}
                <span>Operational Alerts</span>
              </a>
              <a href="reports.html" class="dropdown-item ${path.endsWith('reports.html') ? 'active' : ''}">
                ${getIconSvg('bar-chart-3')}
                <span>Reports & Analytics</span>
              </a>
              <a href="activity-logs.html" class="dropdown-item ${path.endsWith('activity-logs.html') ? 'active' : ''}">
                ${getIconSvg('file-text')}
                <span>Activity Audit Logs</span>
              </a>
            </div>
          </div>

          <!-- 6. Administration -->
          <a href="users.html" class="header-pill-link ${isAdminCat ? 'active' : ''}">
            ${getIconSvg('users')}
            <span>Users</span>
          </a>
        </nav>
      </div>

      <!-- Search & User Actions Group (Right Side) -->
      <div style="display: flex; align-items: center; gap: 14px;">
        <div class="header-search-wrapper">
          <svg class="header-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input type="text" class="header-search-input" id="global-search-input" placeholder="Search... (⌘ K)" onkeyup="handleGlobalSearch(event)">
        </div>

        <div class="header-actions-group">
          <a href="alerts.html" class="header-icon-btn" title="Alert Telemetry (⌘ A)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"></path>
              <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"></path>
            </svg>
            <span class="header-badge-dot"></span>
          </a>

          <div class="header-user-pill">
            <div class="user-avatar" style="width: 32px; height: 32px; font-size: 0.82rem; background: linear-gradient(135deg, #fa7b7b, #e05e5e); color: #fff;">${user.name.charAt(0)}</div>
            <div style="display: flex; flex-direction: column; text-align: left;">
              <span style="font-size: 0.82rem; font-weight: 700; color: var(--text-primary);">${user.name}</span>
              <span style="font-size: 0.68rem; color: #64748b; font-weight: 600;">${user.role}</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  `;
}

// Injects Floating Menu Bar (Matching Reference Image 3 Variants)
function injectDock() {
  const path = window.location.pathname;
  const isAuthPage = path.endsWith("login.html") || path.endsWith("register.html") || path.endsWith("welcome.html");
  if (isAuthPage) return;

  let div = document.getElementById("floating-dock-mount");
  if (!div) {
    div = document.createElement("div");
    div.id = "floating-dock-mount";
    document.body.appendChild(div);
  } else if (div.children.length > 0) {
    return;
  }

  const isDash = path.endsWith("dashboard.html") || path.endsWith("/") || path.endsWith("index.html");
  const isTrace = path.endsWith("traceability.html") || path.endsWith("products.html") || path.endsWith("batches.html") || path.endsWith("materials.html") || path.endsWith("suppliers.html");
  const isComp = path.endsWith("compliance.html") || path.endsWith("reports.html") || path.endsWith("activity-logs.html");
  const isSec = path.endsWith("alerts.html") || path.endsWith("network-security.html") || path.endsWith("network-scan.html");
  const isAdmin = path.endsWith("users.html");

  const currentStyle = localStorage.getItem("sentinelDockStyle") || "style-3";

  div.className = "dock-wrapper";

  div.innerHTML = `
    <!-- 1. Traceability & Supply Chain Popover Menu -->
    <div class="category-popover" id="popover-traceability">
      <div class="category-popover-header">TRACEABILITY & SUPPLY CHAIN</div>
      <a href="traceability.html" class="category-popover-item ${path.endsWith('traceability.html') ? 'active' : ''}">
        ${getIconSvg('git-fork')}
        <span>Traceability Graph</span>
      </a>
      <a href="batches.html" class="category-popover-item ${path.endsWith('batches.html') ? 'active' : ''}">
        ${getIconSvg('layers')}
        <span>Production Batches</span>
      </a>
      <a href="materials.html" class="category-popover-item ${path.endsWith('materials.html') ? 'active' : ''}">
        ${getIconSvg('cubes')}
        <span>Raw Materials & Stock</span>
      </a>
      <a href="products.html" class="category-popover-item ${path.endsWith('products.html') ? 'active' : ''}">
        ${getIconSvg('box')}
        <span>Products Catalog</span>
      </a>
      <a href="suppliers.html" class="category-popover-item ${path.endsWith('suppliers.html') ? 'active' : ''}">
        ${getIconSvg('truck')}
        <span>Suppliers Directory</span>
      </a>
    </div>

    <!-- 2. Compliance & Governance Popover Menu -->
    <div class="category-popover" id="popover-compliance">
      <div class="category-popover-header">REGULATORY & COMPLIANCE</div>
      <a href="compliance.html" class="category-popover-item ${path.endsWith('compliance.html') ? 'active' : ''}">
        ${getIconSvg('shield-check')}
        <span>Compliance Standards</span>
      </a>
      <a href="reports.html" class="category-popover-item ${path.endsWith('reports.html') ? 'active' : ''}">
        ${getIconSvg('bar-chart-3')}
        <span>Audit Reports & Analytics</span>
      </a>
      <a href="activity-logs.html" class="category-popover-item ${path.endsWith('activity-logs.html') ? 'active' : ''}">
        ${getIconSvg('file-text')}
        <span>Activity Audit Trail</span>
      </a>
    </div>

    <!-- 3. Security & Telemetry Popover Menu -->
    <div class="category-popover" id="popover-security">
      <div class="category-popover-header">SECURITY & TELEMETRY</div>
      <a href="alerts.html" class="category-popover-item ${path.endsWith('alerts.html') ? 'active' : ''}">
        ${getIconSvg('bell-ring')}
        <span>Operational Alerts</span>
      </a>
      <a href="network-security.html" class="category-popover-item ${path.endsWith('network-security.html') ? 'active' : ''}">
        ${getIconSvg('shield-alert')}
        <span>Security Monitor SOC</span>
      </a>
      <a href="network-scan.html" class="category-popover-item ${path.endsWith('network-scan.html') ? 'active' : ''}">
        ${getIconSvg('radar')}
        <span>OT & PLC Network Scanner</span>
      </a>
    </div>

    <!-- 4. Administration & System Popover Menu -->
    <div class="category-popover" id="popover-admin">
      <div class="category-popover-header">ADMINISTRATION & SETTINGS</div>
      <a href="users.html" class="category-popover-item ${path.endsWith('users.html') ? 'active' : ''}">
        ${getIconSvg('users')}
        <span>User Administration</span>
      </a>
      <button class="category-popover-item" onclick="openModal('help-telemetry-modal')" style="border:none; background:transparent; width:100%; cursor:pointer; text-align:left;">
        <svg class="nav-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        <span>System Diagnostics</span>
      </button>
      <button class="category-popover-item" onclick="handleLogout()" style="border:none; background:transparent; width:100%; cursor:pointer; color:#ef4444; text-align:left;">
        <svg class="nav-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        <span>Sign Out</span>
      </button>
    </div>

    <!-- Floating Category Menu Bar (Matching Reference Image) -->
    <div class="dock-pill-bar ${currentStyle}" id="dock-pill-bar">
      <!-- Style 2 Floating Notch Dot -->
      <div class="dock-notch-dot" id="dock-notch-dot"></div>

      <!-- 1. Dashboard Tab -->
      <a href="dashboard.html" class="dock-category-btn ${isDash ? 'active' : ''}" data-tab="dashboard" title="Executive Dashboard">
        <div class="dock-icon-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        </div>
        <span class="dock-label">Dashboard</span>
        <div class="dock-active-line"></div>
      </a>

      <!-- 2. Traceability Tab (Categorized Supply Chain Modules) -->
      <button class="dock-category-btn ${isTrace ? 'active' : ''}" id="cat-btn-traceability" onclick="toggleCategoryPopover('traceability', event)" data-tab="traceability" title="Traceability & Supply Chain">
        <div class="dock-icon-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="18" r="3"/>
            <circle cx="6" cy="6" r="3"/>
            <circle cx="18" cy="6" r="3"/>
            <path d="M18 9v1a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9"/>
            <path d="M12 12v3"/>
          </svg>
        </div>
        <span class="dock-label">Traceability</span>
        <div class="dock-active-line"></div>
      </button>

      <!-- 3. Compliance Tab (Categorized Regulatory Modules) -->
      <button class="dock-category-btn ${isComp ? 'active' : ''}" id="cat-btn-compliance" onclick="toggleCategoryPopover('compliance', event)" data-tab="compliance" title="Regulatory Compliance & Audits">
        <div class="dock-icon-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <path d="m9 12 2 2 4-4"/>
          </svg>
        </div>
        <span class="dock-label">Compliance</span>
        <div class="dock-active-line"></div>
      </button>

      <!-- 4. Security Tab (Categorized Telemetry & SOC Modules) -->
      <button class="dock-category-btn ${isSec ? 'active' : ''}" id="cat-btn-security" onclick="toggleCategoryPopover('security', event)" data-tab="security" title="Security & Alert Telemetry">
        <div class="dock-icon-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
          <span class="dock-badge-dot"></span>
        </div>
        <span class="dock-label">Security</span>
        <div class="dock-active-line"></div>
      </button>

      <!-- 5. Admin Tab (User & Credential Settings) -->
      <button class="dock-category-btn ${isAdmin ? 'active' : ''}" id="cat-btn-admin" onclick="toggleCategoryPopover('admin', event)" data-tab="admin" title="Administration & User Settings">
        <div class="dock-icon-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M22 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
        </div>
        <span class="dock-label">Admin</span>
        <div class="dock-active-line"></div>
      </button>

      <!-- Style Switcher Widget (Switch between 1, 2, 3 from user reference image) -->
      <div class="dock-style-switcher">
        <button class="dock-style-btn ${currentStyle === 'style-1' ? 'active' : ''}" onclick="setDockStyle('style-1', event)" title="Style 1: Line Indicator">1</button>
        <button class="dock-style-btn ${currentStyle === 'style-2' ? 'active' : ''}" onclick="setDockStyle('style-2', event)" title="Style 2: Curved Notch Dot">2</button>
        <button class="dock-style-btn ${currentStyle === 'style-3' ? 'active' : ''}" onclick="setDockStyle('style-3', event)" title="Style 3: Soft Pill Box">3</button>
      </div>
    </div>
  `;

  document.body.appendChild(div);

  setTimeout(updateNotchPosition, 50);
  window.addEventListener("resize", updateNotchPosition);

  // Close any category popovers when clicking outside
  document.addEventListener("click", (e) => {
    const popovers = document.querySelectorAll(".category-popover");
    const btns = document.querySelectorAll(".dock-category-btn");

    let clickedInside = false;
    popovers.forEach(p => { if (p.contains(e.target)) clickedInside = true; });
    btns.forEach(b => { if (b.contains(e.target)) clickedInside = true; });

    if (!clickedInside) {
      closeAllCategoryPopovers();
    }
  });
}

function setDockStyle(styleName, e) {
  if (e) e.stopPropagation();
  localStorage.setItem("sentinelDockStyle", styleName);
  const bar = document.getElementById("dock-pill-bar");
  if (bar) {
    bar.className = `dock-pill-bar ${styleName}`;
  }
  const btns = document.querySelectorAll(".dock-style-btn");
  btns.forEach(b => {
    b.classList.toggle("active", b.getAttribute("onclick").includes(styleName));
  });
  updateNotchPosition();
}

function updateNotchPosition() {
  const bar = document.getElementById("dock-pill-bar");
  const dot = document.getElementById("dock-notch-dot");
  if (!bar || !dot) return;
  const activeBtn = bar.querySelector(".dock-category-btn.active");
  if (activeBtn) {
    const btnRect = activeBtn.getBoundingClientRect();
    const barRect = bar.getBoundingClientRect();
    const centerOffset = (btnRect.left - barRect.left) + (btnRect.width / 2);
    dot.style.left = `${centerOffset}px`;
  }
}

function closeAllCategoryPopovers() {
  const popovers = document.querySelectorAll(".category-popover");
  const btns = document.querySelectorAll(".dock-category-btn");
  popovers.forEach(p => p.classList.remove("open"));
  btns.forEach(b => b.classList.remove("popover-open"));
}

function toggleCategoryPopover(category, e) {
  if (e) e.stopPropagation();

  const targetPopover = document.getElementById(`popover-${category}`);
  const targetBtn = document.getElementById(`cat-btn-${category}`);
  const dockWrapper = document.querySelector(".dock-wrapper");

  const isOpen = targetPopover ? targetPopover.classList.contains("open") : false;

  closeAllCategoryPopovers();

  if (!isOpen && targetPopover && targetBtn && dockWrapper) {
    targetPopover.classList.add("open");
    targetBtn.classList.add("popover-open");

    // Center popover relative to the dock wrapper based on target button position
    const btnRect = targetBtn.getBoundingClientRect();
    const wrapRect = dockWrapper.getBoundingClientRect();
    const btnCenterX = (btnRect.left - wrapRect.left) + (btnRect.width / 2);
    targetPopover.style.left = `${btnCenterX}px`;
    targetPopover.style.transform = `translateX(-50%) translateY(0) scale(1)`;
  }
}

function toggleDockPopover(e) {
  if (e) e.stopPropagation();
  const popover = document.getElementById("dock-popover-menu");
  const toggleBtn = document.getElementById("dock-tools-toggle");
  if (popover && toggleBtn) {
    const isOpen = popover.classList.toggle("open");
    toggleBtn.classList.toggle("active", isOpen);
  }
}

function executeDockAction(action) {
  const popover = document.getElementById("dock-popover-menu");
  if (popover) popover.classList.remove("open");

  switch (action) {
    case "share-file":
      showToast("Preparing Sentinel-Trace PDF Audit Report...", "info");
      setTimeout(() => { window.location.href = "reports.html"; }, 600);
      break;
    case "open-link":
      showToast("Opening Supply Chain Traceability Graph...", "info");
      setTimeout(() => { window.location.href = "traceability.html"; }, 600);
      break;
    case "embed-tool":
      showToast("Launching Network Subnet Scanner...", "info");
      setTimeout(() => { window.location.href = "network-scan.html"; }, 600);
      break;
    case "add-agenda":
      showToast("Opening Regulatory Compliance Manager...", "info");
      setTimeout(() => { window.location.href = "compliance.html"; }, 600);
      break;
    case "share-screen":
      showToast("Opening Security Monitor SOC Feed...", "info");
      setTimeout(() => { window.location.href = "network-security.html"; }, 600);
      break;
    default:
      break;
  }
}

// Global Keyboard Shortcut Listener
function initShortcutListeners() {
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAllCategoryPopovers();
      return;
    }

    // Check for Cmd (Mac) or Ctrl (Windows)
    if (e.metaKey || e.ctrlKey) {
      const key = e.key.toLowerCase();
      if (key === "k") {
        e.preventDefault();
        toggleDockPopover();
      } else if (key === "d") {
        e.preventDefault();
        window.location.href = "dashboard.html";
      } else if (key === "t") {
        e.preventDefault();
        window.location.href = "traceability.html";
      } else if (key === "c") {
        e.preventDefault();
        window.location.href = "compliance.html";
      } else if (key === "e") {
        e.preventDefault();
        window.location.href = "network-scan.html";
      } else if (key === "w") {
        e.preventDefault();
        window.location.href = "network-security.html";
      } else if (key === "a") {
        e.preventDefault();
        window.location.href = "alerts.html";
      } else if (key === "r") {
        e.preventDefault();
        window.location.href = "reports.html";
      } else if (key === "u") {
        e.preventDefault();
        window.location.href = "users.html";
      }
    }
  });
}

// Mobile Sidebar Toggle
function toggleMobileSidebar() {
  const sidebar = document.getElementById("app-sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (sidebar && backdrop) {
    sidebar.classList.toggle("mobile-open");
    backdrop.classList.toggle("active");
  }
}

// User Sign Out
function handleLogout() {
  if (confirm("Are you sure you want to sign out of Sentinel-Trace?")) {
    localStorage.removeItem("sentinelToken");
    window.location.href = "login.html";
  }
}

// Global Toast System
function initToastContainer() {
  if (!document.getElementById("toast-container")) {
    const div = document.createElement("div");
    div.id = "toast-container";
    document.body.appendChild(div);
  }
}

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div style="flex-grow: 1;">${message}</div>
    <button onclick="this.parentElement.remove()" style="color: #94a3b8; font-size: 1.1rem; cursor: pointer;">&times;</button>
  `;

  container.appendChild(toast);
  setTimeout(() => toast.classList.add("show"), 10);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}

// Modal System Helper
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove("active");
    document.body.style.overflow = "auto";
  }
}

// Global Search Listener
function handleGlobalSearch(e) {
  if (e.key === "Enter") {
    const q = e.target.value.trim().toLowerCase();
    if (!q) return;
    showToast(`Searching Sentinel-Trace repositories for: "${q}"`, "info");
    const activeTable = document.querySelector(".data-table tbody");
    if (activeTable) {
      const rows = activeTable.querySelectorAll("tr");
      rows.forEach(r => {
        const text = r.textContent.toLowerCase();
        r.style.display = text.includes(q) ? "" : "none";
      });
    }
  }
}

// SVG Icon Generator Helper
function getIconSvg(name) {
  const icons = {
    "layout-dashboard": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>`,
    "git-fork": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><circle cx="18" cy="6" r="3"></circle><path d="M18 9v1a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9"></path><path d="M12 12v3"></path></svg>`,
    "box": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`,
    "layers": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>`,
    "cubes": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>`,
    "truck": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3" width="15" height="13"></rect><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"></polygon><circle cx="5.5" cy="18.5" r="2.5"></circle><circle cx="18.5" cy="18.5" r="2.5"></circle></svg>`,
    "shield-check": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><polyline points="9 12 11 14 15 10"></polyline></svg>`,
    "radar": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19.07 4.93a10 10 0 0 0-14.14 0"></path><path d="M16.24 7.76a6 6 0 0 0-8.48 0"></path><circle cx="12" cy="12" r="2"></circle><line x1="12" y1="12" x2="20" y2="4"></line></svg>`,
    "shield-alert": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
    "bell-ring": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path><path d="M2 8c0-2.2 1.8-4 4-4"></path><path d="M22 8c0-2.2-1.8-4-4-4"></path></svg>`,
    "bar-chart-3": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>`,
    "file-text": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`,
    "users": `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>`
  };
  return icons[name] || `<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle></svg>`;
}
