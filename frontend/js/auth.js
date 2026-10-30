/* ===================================================================
   SENTINEL-TRACE AUTHENTICATION LOGIC (Login & Register)
   Handles Credentials Submission, Clearing, Autofill, and Dashboard Routing
   =================================================================== */

function initAuth() {
  // Remember Me Auto-fill
  const remembered = localStorage.getItem("sentinel_remembered_email");
  const emailInput = document.getElementById("login-email");
  const rememberCheckbox = document.querySelector(".auth-remember-checkbox input");
  if (remembered && emailInput) {
    emailInput.value = remembered;
    if (rememberCheckbox) rememberCheckbox.checked = true;
  }

  // Single-submission locks
  let isLoggingIn = false;
  let isRegistering = false;

  // Login Form Handler
  const loginForm = document.getElementById("login-form");
  const submitBtn = document.getElementById("login-btn");

  async function performLogin(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isLoggingIn) return;

    const email = document.getElementById("login-email") ? document.getElementById("login-email").value.trim() : "";
    const password = document.getElementById("login-password") ? document.getElementById("login-password").value : "";
    const isRemember = rememberCheckbox ? rememberCheckbox.checked : true;

    if (!email || !password) {
      showToast("Please enter both email and password.", "danger");
      return;
    }

    if (isRemember) {
      localStorage.setItem("sentinel_remembered_email", email);
    } else {
      localStorage.removeItem("sentinel_remembered_email");
    }

    isLoggingIn = true;
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Verifying Credentials...</span>`;
    }

    try {
      const res = await apiLogin(email, password);
      if (res && (res.token || res.access_token || res.success)) {
        const userObj = res.user || {};
        const displayName = userObj.username || userObj.name || 'Operator';
        showToast(`Welcome back, ${displayName}! Redirecting to dashboard...`, "success");
        setTimeout(() => {
          window.location.href = "dashboard.html";
        }, 500);
      } else {
        const errorMsg = (res && (res.message || res.error)) ? (res.message || res.error) : "Authentication failed. Check credentials.";
        showToast(errorMsg, "danger");
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = `Login`;
        }
        isLoggingIn = false;
      }
    } catch (err) {
      const msg = err.message || "Operation failed";
      showToast("Authentication error: " + msg, "danger");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `Login`;
      }
      isLoggingIn = false;
    }
  }

  if (loginForm) {
    loginForm.addEventListener("submit", performLogin);
  }
  if (submitBtn) {
    submitBtn.addEventListener("click", (e) => {
      // If inside form, submit event handles it; but if form submission was prevented or detached, trigger performLogin
      if (!loginForm) performLogin(e);
    });
  }

  // Register Form Handler
  const registerForm = document.getElementById("register-form");
  const regSubmitBtn = document.getElementById("register-btn");

  async function performRegister(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (isRegistering) return;

    const username = document.getElementById("reg-username") ? document.getElementById("reg-username").value.trim() : "";
    const email = document.getElementById("reg-email") ? document.getElementById("reg-email").value.trim() : "";
    const password = document.getElementById("reg-password") ? document.getElementById("reg-password").value : "";
    const confirmPass = document.getElementById("reg-confirm-password") ? document.getElementById("reg-confirm-password").value : "";
    const role = document.getElementById("reg-role") ? document.getElementById("reg-role").value : "";

    if (!username || !email || !password || !role) {
      showToast("Please complete all required fields.", "danger");
      return;
    }

    if (password !== confirmPass) {
      showToast("Passwords do not match.", "danger");
      return;
    }

    isRegistering = true;
    if (regSubmitBtn) {
      regSubmitBtn.disabled = true;
      regSubmitBtn.innerHTML = `<span>Registering Account...</span>`;
    }

    try {
      await apiRegister(username, email, password, role);
      showToast("Account successfully registered! Redirecting to login...", "success");
      setTimeout(() => {
        window.location.href = "login.html";
      }, 1000);
    } catch (err) {
      showToast("Registration error: " + (err.message || "Failed to register"), "danger");
      if (regSubmitBtn) {
        regSubmitBtn.disabled = false;
        regSubmitBtn.innerHTML = `<span>Create Account</span>`;
      }
      isRegistering = false;
    }
  }

  if (registerForm) {
    registerForm.addEventListener("submit", performRegister);
  }
}

if (typeof onReady === "function") {
  onReady(initAuth);
} else if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAuth);
} else {
  initAuth();
}

// Clear Credentials Helper
function clearCredentials() {
  const emailInput = document.getElementById("login-email");
  const passInput = document.getElementById("login-password");
  if (emailInput) {
    emailInput.value = "";
    emailInput.focus();
  }
  if (passInput) passInput.value = "";
  showToast("Credentials cleared.", "info");
}

// Quick Preset Credentials Helper
function fillCredentials(email, password) {
  const emailInput = document.getElementById("login-email");
  const passInput = document.getElementById("login-password");
  if (emailInput) emailInput.value = email;
  if (passInput) passInput.value = password;
  showToast(`Loaded credentials for ${email}`, "info");
}

async function handleForgotPassword(e) {
  if (e && e.preventDefault) e.preventDefault();

  const emailInput = document.getElementById("login-email");
  let email = emailInput ? emailInput.value.trim() : "";

  if (!email || !email.includes("@")) {
    const promptVal = prompt("Enter your registered Sentinel-Trace account email for password recovery:", email);
    if (!promptVal || !promptVal.trim()) {
      return;
    }
    email = promptVal.trim();
  }

  try {
    showToast(`Dispatching password recovery request for ${email}...`, "info");
    const res = await (window.apiForgotPassword ? window.apiForgotPassword(email) : apiRequest("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email })
    }));

    showToast(res?.message || `Password recovery instructions dispatched to ${email}.`, "success");
  } catch (err) {
    showToast(`Password recovery failed: ${err.message}`, "danger");
  }
}

window.handleForgotPassword = handleForgotPassword;
window.fillCredentials = fillCredentials;
window.clearCredentials = clearCredentials;
