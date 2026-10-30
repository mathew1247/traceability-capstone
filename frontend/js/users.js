/* ===================================================================
   SENTINEL-TRACE USER MANAGEMENT CONTROLLER (Admin Only)
   Role-Based Access Control (Admin, Inspector, Auditor, Operator)
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadUsersTable();
  initUserModalForm();
  initEditUserForm();
});

async function loadUsersTable() {
  const users = await getUsers();
  const tbody = document.getElementById("users-table-body");
  if (!tbody) return;

  let html = "";
  users.forEach(u => {
    let roleBadge = "badge-neutral";
    if (u.role === "Admin") roleBadge = "badge-danger";
    else if (u.role === "Inspector") roleBadge = "badge-info";
    else if (u.role === "Auditor") roleBadge = "badge-warning";
    else if (u.role === "Operator") roleBadge = "badge-success";

    const isUserActive = u.status === "Active";

    html += `
      <tr>
        <td>
          <div style="display: flex; align-items: center; gap: 10px;">
            <div class="user-avatar" style="width: 34px; height: 34px; font-size: 0.82rem;">${u.name.charAt(0)}</div>
            <div>
              <div class="td-primary-text">${u.name}</div>
              <div class="td-secondary-text">ID: ${u.id}</div>
            </div>
          </div>
        </td>
        <td>${u.email}</td>
        <td><span class="badge ${roleBadge}">${u.role}</span></td>
        <td>
          <span class="badge ${isUserActive ? 'badge-success' : 'badge-neutral'}">
            <span class="badge-dot"></span>${u.status}
          </span>
        </td>
        <td>${u.createdDate || '2026-03-01'}</td>
        <td class="table-actions-cell" style="display: flex; align-items: center; gap: 6px;">
          <button class="btn btn-secondary btn-sm" style="padding: 4px 10px; font-size: 0.75rem;" onclick="handleToggleStatus('${u.id}')">
            ${isUserActive ? 'Disable' : 'Enable'}
          </button>
          <button class="btn-table-action" title="Edit User" onclick="handleEditUser('${u.id}')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
          </button>
          <button class="btn-table-action danger" title="Delete User" onclick="handleDeleteUser('${u.id}')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

function initUserModalForm() {
  const form = document.getElementById("add-user-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("usr-name").value.trim();
    const email = document.getElementById("usr-email").value.trim();
    const role = document.getElementById("usr-role").value;

    await createUser({ name, email, role, status: "Active" });
    closeModal("add-user-modal");
    form.reset();
    showToast(`User account created for ${name} (${role})!`, "success");
    await loadUsersTable();
  });
}

async function handleToggleStatus(id) {
  try {
    const updated = await toggleUserStatus(id);
    showToast(`Account status updated to: ${updated.status}`, "info");
    await loadUsersTable();
  } catch (err) {
    showToast(`Failed to toggle user status: ${err.message}`, "danger");
  }
}

async function handleEditUser(id) {
  try {
    const users = await getUsers();
    const user = users.find(u => u.id === id);
    if (!user) {
      showToast("User not found.", "danger");
      return;
    }
    document.getElementById("edit-usr-id").value = user.id;
    document.getElementById("edit-usr-name").value = user.name || user.username || "";
    document.getElementById("edit-usr-email").value = user.email || "";
    document.getElementById("edit-usr-role").value = user.role || "Operator";
    document.getElementById("edit-usr-status").value = user.status || "Active";
    openModal("edit-user-modal");
  } catch (err) {
    showToast(`Failed to load user details: ${err.message}`, "danger");
  }
}

function initEditUserForm() {
  const form = document.getElementById("edit-user-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("edit-usr-id").value;
    const name = document.getElementById("edit-usr-name").value.trim();
    const email = document.getElementById("edit-usr-email").value.trim();
    const role = document.getElementById("edit-usr-role").value;
    const status = document.getElementById("edit-usr-status").value;

    if (!name || !email) {
      showToast("Name and email are required.", "danger");
      return;
    }

    try {
      await updateUser(id, { name, email, role, status });
      closeModal("edit-user-modal");
      showToast(`User ${name} updated successfully!`, "success");
      await loadUsersTable();
    } catch (err) {
      showToast(`Failed to update user: ${err.message}`, "danger");
    }
  });
}

async function handleDeleteUser(id) {
  if (confirm(`Are you sure you want to delete user ${id}?`)) {
    try {
      await deleteUser(id);
      showToast(`User ${id} removed successfully.`, "info");
      await loadUsersTable();
    } catch (err) {
      showToast(`Failed to delete user: ${err.message}`, "danger");
    }
  }
}

function filterUsers() {
  const query = document.getElementById("user-search").value.toLowerCase();
  const rows = document.querySelectorAll("#users-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  });
}
