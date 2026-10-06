/* ===================================================================
   SENTINEL-TRACE USER MANAGEMENT CONTROLLER (Admin Only)
   Role-Based Access Control (Admin, Inspector, Auditor, Operator)
   =================================================================== */

document.addEventListener("DOMContentLoaded", async () => {
  await loadUsersTable();
  initUserModalForm();
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
        <td class="table-actions-cell">
          <button class="btn btn-secondary btn-sm" style="padding: 4px 10px; font-size: 0.75rem;" onclick="handleToggleStatus('${u.id}')">
            ${isUserActive ? 'Disable' : 'Enable'}
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
  const updated = await toggleUserStatus(id);
  showToast(`Account status updated to: ${updated.status}`, "info");
  await loadUsersTable();
}

function filterUsers() {
  const query = document.getElementById("user-search").value.toLowerCase();
  const rows = document.querySelectorAll("#users-table-body tr");

  rows.forEach(r => {
    const text = r.textContent.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  });
}
