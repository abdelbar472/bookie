(() => {
  const { headers, assertLoggedIn, api, setStatus } = window.Bookbox;

  const els = {
    status: document.getElementById('status'),
    output: document.getElementById('output'),
    targetId: document.getElementById('target-id'),
    statsId: document.getElementById('stats-id'),
    followBtn: document.getElementById('follow-btn'),
    unfollowBtn: document.getElementById('unfollow-btn'),
    checkBtn: document.getElementById('check-btn'),
    statsBtn: document.getElementById('stats-btn'),
    followersBtn: document.getElementById('followers-btn'),
    followingBtn: document.getElementById('following-btn'),
  };

  const show = (obj) => { els.output.textContent = JSON.stringify(obj, null, 2); };
  const target = () => Number(els.targetId.value || 0);
  const statsUser = () => Number(els.statsId.value || 0);

  function requireValidUserId(value, label) {
    if (!Number.isInteger(value) || value <= 0) {
      throw new Error(`${label} must be a positive integer user id`);
    }
  }

  els.followBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const followee = target();
      requireValidUserId(followee, 'Target id');
      const res = await api('follow', `api/v1/follow/${followee}`, { method: 'POST', headers: headers() });
      show(res);
      setStatus(els.status, 'Followed user');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.unfollowBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const followee = target();
      requireValidUserId(followee, 'Target id');
      await api('follow', `api/v1/follow/${followee}`, { method: 'DELETE', headers: headers() });
      show({ ok: true });
      setStatus(els.status, 'Unfollowed user');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.checkBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const followee = target();
      requireValidUserId(followee, 'Target id');
      const res = await api('follow', `api/v1/follow/check/${followee}`, { headers: headers() });
      show(res);
      setStatus(els.status, 'Loaded follow check');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.statsBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const userId = statsUser();
      requireValidUserId(userId, 'Stats user id');
      const res = await api('follow', `api/v1/follow/users/${userId}/stats`, { headers: headers() });
      show(res);
      setStatus(els.status, 'Loaded follow stats');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.followersBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const userId = statsUser();
      requireValidUserId(userId, 'Stats user id');
      const res = await api('follow', `api/v1/follow/users/${userId}/followers?skip=0&limit=20`, { headers: headers() });
      show(res);
      setStatus(els.status, 'Loaded followers');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.followingBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const userId = statsUser();
      requireValidUserId(userId, 'Stats user id');
      const res = await api('follow', `api/v1/follow/users/${userId}/following?skip=0&limit=20`, { headers: headers() });
      show(res);
      setStatus(els.status, 'Loaded following');
    } catch (err) { setStatus(els.status, err.message, true); }
  };
})();

