(() => {
  const { headers, assertLoggedIn, api, setStatus } = window.Bookbox;

  const els = {
    status: document.getElementById('status'),
    output: document.getElementById('output'),
    isbn: document.getElementById('isbn'),
    rating: document.getElementById('rating'),
    reviewTitle: document.getElementById('review-title'),
    reviewContent: document.getElementById('review-content'),
    likeBtn: document.getElementById('like-btn'),
    statsBtn: document.getElementById('stats-btn'),
    rateBtn: document.getElementById('rate-btn'),
    reviewBtn: document.getElementById('review-btn'),
    listReviewsBtn: document.getElementById('list-reviews-btn'),
  };

  const show = (obj) => { els.output.textContent = JSON.stringify(obj, null, 2); };
  const isbn = () => encodeURIComponent(els.isbn.value.trim());

  function requireIsbn() {
    const raw = els.isbn.value.trim();
    if (!raw) {
      throw new Error('ISBN is required');
    }
    return raw;
  }

  els.likeBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const rawIsbn = requireIsbn();
      const res = await api('social', `api/v1/social/likes/${encodeURIComponent(rawIsbn)}`, { method: 'POST', headers: headers() });
      show(res);
      setStatus(els.status, 'Book liked');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.statsBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const rawIsbn = requireIsbn();
      const res = await api('social', `api/v1/social/books/${encodeURIComponent(rawIsbn)}/stats`, { headers: headers() });
      show(res);
      setStatus(els.status, 'Book social stats loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.rateBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const rawIsbn = requireIsbn();
      const res = await api('social', `api/v1/social/ratings/${encodeURIComponent(rawIsbn)}`, {
        method: 'PUT',
        headers: headers(true),
        body: JSON.stringify({ rating: Number(els.rating.value) }),
      });
      show(res);
      setStatus(els.status, 'Book rated');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.reviewBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const rawIsbn = requireIsbn();
      const title = els.reviewTitle.value.trim();
      const content = els.reviewContent.value.trim();
      if (title.length < 3) throw new Error('Review title must be at least 3 characters');
      if (content.length < 10) throw new Error('Review content must be at least 10 characters');
      const res = await api('social', 'api/v1/social/reviews', {
        method: 'POST',
        headers: headers(true),
        body: JSON.stringify({
          isbn: rawIsbn,
          title,
          content,
        }),
      });
      show(res);
      setStatus(els.status, 'Review created');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.listReviewsBtn.onclick = async () => {
    try {
      assertLoggedIn();
      const rawIsbn = requireIsbn();
      const res = await api('social', `api/v1/social/books/${encodeURIComponent(rawIsbn)}/reviews?skip=0&limit=20`, {
        headers: headers(),
      });
      show(res);
      setStatus(els.status, 'Book reviews loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };
})();

