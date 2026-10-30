/* ===================================================================
   SENTINEL-TRACE SHARED PAGINATION COMPONENT
   Universal Pagination, Page-Size, Filter, Search, and Race-Condition Engine
   =================================================================== */

function createPaginationController({
  moduleName,
  fetchFunction,
  renderTableFunction,
  searchInputId,
  filterSelectId,
  pageSizeSelectId,
  infoElementId,
  prevBtnId,
  nextBtnId,
  pageNumbersContainerId,
  defaultPageSize = 10,
  defaultSortBy = 'created_at',
  defaultSortOrder = 'desc'
}) {
  const state = {
    page: 1,
    pageSize: defaultPageSize,
    search: '',
    status: '',
    sortBy: defaultSortBy,
    sortOrder: defaultSortOrder,
    total: 0,
    totalPages: 0,
    isLoading: false,
    requestId: 0
  };

  let searchDebounceTimeout = null;

  async function loadData() {
    state.requestId++;
    const currentReq = state.requestId;
    state.isLoading = true;

    const tbody = document.getElementById(`${moduleName}-table-body`);
    if (tbody && state.page === 1 && !state.search && tbody.children.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 24px; color: var(--text-secondary);">Loading ${moduleName}...</td></tr>`;
    }

    try {
      const result = await fetchFunction({
        page: state.page,
        pageSize: state.pageSize,
        search: state.search,
        status: state.status,
        sortBy: state.sortBy,
        sortOrder: state.sortOrder
      });

      // Avoid race conditions: discard response if newer request already issued
      if (currentReq !== state.requestId) return;

      state.total = result.total !== undefined ? result.total : result.length;
      state.totalPages = result.totalPages !== undefined ? result.totalPages : (state.total > 0 ? Math.ceil(state.total / state.pageSize) : 0);
      state.page = result.page !== undefined ? result.page : state.page;
      state.isLoading = false;

      // Render records for current page
      renderTableFunction(result.items || result);

      // Render pagination UI controls
      renderControls();
      return result;
    } catch (err) {
      if (currentReq !== state.requestId) return;
      state.isLoading = false;
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 24px; color: #ef4444;">Failed to load data: ${err.message}</td></tr>`;
      }
      renderControls();
      throw err;
    }
  }

  function renderControls() {
    const infoEl = document.getElementById(infoElementId);
    const prevBtn = document.getElementById(prevBtnId);
    const nextBtn = document.getElementById(nextBtnId);
    const pageNumbersEl = document.getElementById(pageNumbersContainerId);

    if (infoEl) {
      if (state.total === 0) {
        infoEl.textContent = `Showing 0 of 0 records`;
      } else {
        const start = (state.page - 1) * state.pageSize + 1;
        const end = Math.min(state.page * state.pageSize, state.total);
        infoEl.textContent = `Showing ${start} to ${end} of ${state.total} records`;
      }
    }

    if (prevBtn) {
      prevBtn.disabled = (state.page <= 1 || state.isLoading);
    }
    if (nextBtn) {
      nextBtn.disabled = (state.page >= state.totalPages || state.totalPages === 0 || state.isLoading);
    }

    if (pageNumbersEl) {
      pageNumbersEl.innerHTML = "";
      if (state.totalPages <= 0) return;

      const total = state.totalPages;
      const current = state.page;

      // Compact pagination button list with ellipsis for large ranges
      const pages = [];
      if (total <= 7) {
        for (let i = 1; i <= total; i++) pages.push(i);
      } else {
        pages.push(1);
        if (current > 3) pages.push("...");
        const start = Math.max(2, current - 1);
        const end = Math.min(total - 1, current + 1);
        for (let i = start; i <= end; i++) pages.push(i);
        if (current < total - 2) pages.push("...");
        pages.push(total);
      }

      pages.forEach(p => {
        if (p === "...") {
          const span = document.createElement("span");
          span.style.padding = "0 4px";
          span.style.color = "var(--text-secondary)";
          span.textContent = "...";
          pageNumbersEl.appendChild(span);
        } else {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = `pagination-btn ${p === current ? "active" : ""}`;
          btn.textContent = p;
          if (p === current) {
            btn.disabled = true;
          } else {
            btn.onclick = () => {
              state.page = p;
              loadData();
            };
          }
          pageNumbersEl.appendChild(btn);
        }
      });
    }
  }

  function initListeners() {
    const prevBtn = document.getElementById(prevBtnId);
    if (prevBtn) {
      prevBtn.onclick = () => {
        if (state.page > 1) {
          state.page--;
          loadData();
        }
      };
    }

    const nextBtn = document.getElementById(nextBtnId);
    if (nextBtn) {
      nextBtn.onclick = () => {
        if (state.page < state.totalPages) {
          state.page++;
          loadData();
        }
      };
    }

    const pageSizeSelect = document.getElementById(pageSizeSelectId);
    if (pageSizeSelect) {
      pageSizeSelect.value = String(state.pageSize);
      pageSizeSelect.onchange = (e) => {
        state.pageSize = parseInt(e.target.value, 10) || defaultPageSize;
        state.page = 1; // Reset to page 1 on page size change
        loadData();
      };
    }

    const searchInput = document.getElementById(searchInputId);
    if (searchInput) {
      searchInput.oninput = (e) => {
        clearTimeout(searchDebounceTimeout);
        searchDebounceTimeout = setTimeout(() => {
          state.search = e.target.value.trim();
          state.page = 1; // Reset to page 1 when search query changes
          loadData();
        }, 250);
      };
    }

    const filterSelect = document.getElementById(filterSelectId);
    if (filterSelect) {
      filterSelect.onchange = (e) => {
        state.status = e.target.value.trim();
        state.page = 1; // Reset to page 1 when filter changes
        loadData();
      };
    }
  }

  function reload(keepPage = false) {
    if (!keepPage) state.page = 1;
    return loadData();
  }

  return {
    init: () => {
      initListeners();
      return loadData();
    },
    reload,
    loadData,
    getState: () => ({ ...state }),
    setPage: (p) => {
      state.page = p;
      return loadData();
    }
  };
}

window.createPaginationController = createPaginationController;
