/* ===================================================================
   SENTINEL-TRACE AUTHENTICATION LOGIC (Login & Register)
   Handles Credentials Submission, Clearing, Autofill, and Dashboard Routing
   =================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  // Login Form Handler
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = document.getElementById("login-email").value.trim();
      const password = document.getElementById("login-password").value;
      const submitBtn = document.getElementById("login-btn");

      if (!email || !password) {
        showToast("Please enter both email and password.", "danger");
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Verifying Credentials...</span>`;

      try {
        const res = await apiLogin(email, password);
        if (res && res.token) {
          showToast(`Welcome back, ${res.user ? res.user.name : 'Operator'}! Redirecting to dashboard...`, "success");
          setTimeout(() => {
            window.location.href = "dashboard.html";
          }, 600);
        } else {
          showToast("Authentication failed. Check credentials.", "danger");
          submitBtn.disabled = false;
          submitBtn.innerHTML = `<span>Authenticate & Open Dashboard</span>`;
        }
      } catch (err) {
        showToast("Authentication error: " + err.message, "danger");
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>Authenticate & Open Dashboard</span>`;
      }
    });
  }

  // Register Form Handler
  const registerForm = document.getElementById("register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = document.getElementById("reg-username").value.trim();
      const email = document.getElementById("reg-email").value.trim();
      const password = document.getElementById("reg-password").value;
      const confirmPass = document.getElementById("reg-confirm-password").value;
      const role = document.getElementById("reg-role").value;
      const submitBtn = document.getElementById("register-btn");

      if (!username || !email || !password || !role) {
        showToast("Please complete all required fields.", "danger");
        return;
      }

      if (password !== confirmPass) {
        showToast("Passwords do not match.", "danger");
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Registering Account...</span>`;

      try {
        await apiRegister(username, email, password, role);
        showToast("Account successfully registered! Redirecting to login...", "success");
        setTimeout(() => {
          window.location.href = "login.html";
        }, 1000);
      } catch (err) {
        showToast("Registration error: " + err.message, "danger");
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>Create Account</span>`;
      }
    });
  }
});

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
