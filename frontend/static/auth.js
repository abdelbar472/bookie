(() => {
  const { state, headers, api, login, setStatus } = window.Bookbox;

  const els = {
    status: document.getElementById('auth-status'),
    output: document.getElementById('output'),
    regEmail: document.getElementById('reg-email'),
    regUsername: document.getElementById('reg-username'),
    regFullname: document.getElementById('reg-fullname'),
    regPassword: document.getElementById('reg-password'),
    registerBtn: document.getElementById('register-btn'),
    loginUsername: document.getElementById('login-username'),
    loginPassword: document.getElementById('login-password'),
    loginBtn: document.getElementById('login-btn'),
    verifyBtn: document.getElementById('verify-btn'),
    logoutBtn: document.getElementById('logout-btn'),
  };

  function show(obj) {
    els.output.textContent = JSON.stringify(obj, null, 2);
  }

  els.registerBtn.onclick = async () => {
    try {
      const res = await api('auth', 'api/v1/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: els.regEmail.value.trim(),
          username: els.regUsername.value.trim(),
          full_name: els.regFullname.value.trim(),
          password: els.regPassword.value,
        }),
      });
      show(res);
      setStatus(els.status, 'Registered user');
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };

  els.loginBtn.onclick = async () => {
    try {
      const res = await login(els.loginUsername.value.trim(), els.loginPassword.value);
      show(res);
      setStatus(els.status, `Logged in as ${els.loginUsername.value.trim()}`);
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };

  els.verifyBtn.onclick = async () => {
    try {
      const res = await api('auth', 'api/v1/verify', { headers: headers() });
      show(res);
      setStatus(els.status, 'Token verified');
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };

  els.logoutBtn.onclick = async () => {
    try {
      const refreshToken = prompt('Refresh token for logout');
      const res = await api('auth', 'api/v1/logout', {
        method: 'POST',
        headers: headers(true),
        body: JSON.stringify({ refresh_token: refreshToken || '' }),
      });
      localStorage.removeItem('bookbox_token');
      state.token = '';
      show(res);
      setStatus(els.status, 'Logged out');
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };

  if (state.token) setStatus(els.status, 'Token loaded from local storage');
})();

