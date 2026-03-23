window.Bookbox = (() => {
  const state = {
    token: localStorage.getItem('bookbox_token') || '',
    selectedIsbn: null,
    books: [],
    expandedThreads: new Set(),
  };

  function headers(json = false) {
    const h = {};
    if (json) h['Content-Type'] = 'application/json';
    if (state.token) h.Authorization = `Bearer ${state.token}`;
    return h;
  }

  function assertLoggedIn() {
    if (!state.token) throw new Error('Login required for this action');
  }

  async function api(service, path, options = {}) {
    const resp = await fetch(`/api/${service}/${path}`, options);
    const text = await resp.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }
    if (!resp.ok) {
      const detail = data?.detail || data || `${resp.status} ${resp.statusText}`;
      throw new Error(String(detail));
    }
    return data;
  }

  async function login(username, password) {
    const data = await api('auth', 'api/v1/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    state.token = data.access_token;
    localStorage.setItem('bookbox_token', state.token);
    return data;
  }

  function setStatus(el, message, isError = false) {
    if (!el) return;
    el.textContent = message;
    el.style.color = isError ? 'var(--danger)' : 'var(--muted)';
  }

  return {
    state,
    headers,
    assertLoggedIn,
    api,
    login,
    setStatus,
  };
})();

