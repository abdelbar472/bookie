(() => {
  const { headers, assertLoggedIn, api, setStatus } = window.Bookbox;

  const els = {
    status: document.getElementById('status'),
    output: document.getElementById('output'),
    meBtn: document.getElementById('me-btn'),
    bio: document.getElementById('bio'),
    avatar: document.getElementById('avatar'),
    updateMeBtn: document.getElementById('update-me-btn'),
    lookupUsername: document.getElementById('lookup-username'),
    lookupBtn: document.getElementById('lookup-btn'),
  };

  const show = (obj) => { els.output.textContent = JSON.stringify(obj, null, 2); };

  els.meBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const res = await api('user', 'api/v1/me', { headers: headers() });
      show(res);
      setStatus(els.status, 'Loaded /me');
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };

  els.updateMeBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const res = await api('user', 'api/v1/me', {
        method: 'PATCH',
        headers: headers(true),
        body: JSON.stringify({ bio: els.bio.value, avatar_url: els.avatar.value }),
      });
      show(res);
      setStatus(els.status, 'Profile updated');
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };

  els.lookupBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const username = els.lookupUsername.value.trim();
      const res = await api('user', `api/v1/users/${encodeURIComponent(username)}`, { headers: headers() });
      show(res);
      setStatus(els.status, 'User loaded');
    } catch (err) {
      setStatus(els.status, err.message, true);
    }
  };
})();

