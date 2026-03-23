(() => {
  const { state, headers, assertLoggedIn, api, login, setStatus } = window.Bookbox;

  const els = {
    authStatus: document.getElementById('auth-status'),
    loginForm: document.getElementById('login-form'),
    username: document.getElementById('username'),
    password: document.getElementById('password'),
    bookSearch: document.getElementById('book-search'),
    booksGrid: document.getElementById('books-grid'),
    selectedIsbn: document.getElementById('selected-isbn'),
    reviews: document.getElementById('reviews'),
    reviewTemplate: document.getElementById('review-template'),
  };

  let searchTimer = null;

  function renderBookList(items) {
    els.booksGrid.innerHTML = '';
    if (!items.length) {
      els.booksGrid.innerHTML = '<p class="muted">No books found.</p>';
      return;
    }

    items.forEach((book) => {
      const row = document.createElement('div');
      row.className = 'shelf-item';
      row.innerHTML = `<strong>${book.title}</strong><span class="muted">${book.year}</span>`;
      row.onclick = () => selectBook(book.isbn);
      els.booksGrid.appendChild(row);
    });
  }

  function buildReviewCard(review, isReply = false) {
    const node = els.reviewTemplate.content.firstElementChild.cloneNode(true);
    const likeBtn = node.querySelector('.like-review');
    const replyToggleBtn = node.querySelector('.reply-toggle');
    const threadBtn = node.querySelector('.thread-toggle');
    const replyBox = node.querySelector('.reply-box');
    const replyTitle = node.querySelector('.reply-title');
    const replyContent = node.querySelector('.reply-content');
    const submitReply = node.querySelector('.submit-reply');
    const repliesContainer = node.querySelector('.replies');

    node.querySelector('.review-title').textContent = review.title;
    node.querySelector('.review-meta').textContent = `user #${review.user_id}`;
    node.querySelector('.review-content').textContent = review.content;
    node.querySelector('.counters').textContent = `likes ${review.likes_count} · replies ${review.replies_count}`;

    likeBtn.onclick = async () => {
      try {
        assertLoggedIn();
        await api('social', `api/v1/social/reviews/${review.id}/likes`, { method: 'POST', headers: headers() });
        await loadReviews();
      } catch (err) {
        alert(err.message);
      }
    };

    if (isReply) {
      replyToggleBtn.remove();
      threadBtn.remove();
      replyBox.remove();
      repliesContainer.remove();
      return node;
    }

    replyToggleBtn.onclick = () => replyBox.classList.toggle('hidden');

    submitReply.onclick = async () => {
      try {
        assertLoggedIn();
        await api('social', `api/v1/social/reviews/${review.id}/replies`, {
          method: 'POST',
          headers: headers(true),
          body: JSON.stringify({
            title: replyTitle.value || 'Reply',
            content: replyContent.value,
          }),
        });
        state.expandedThreads.add(review.id);
        await loadReviews();
      } catch (err) {
        alert(err.message);
      }
    };

    if ((review.replies_count || 0) <= 0) {
      threadBtn.disabled = true;
      threadBtn.textContent = 'No replies';
      return node;
    }

    const expanded = state.expandedThreads.has(review.id);
    threadBtn.textContent = expanded
      ? `Hide replies (${review.replies_count})`
      : `Show replies (${review.replies_count})`;
    if (!expanded) repliesContainer.classList.add('hidden');

    threadBtn.onclick = async () => {
      const isExpanded = state.expandedThreads.has(review.id);
      if (isExpanded) {
        state.expandedThreads.delete(review.id);
        repliesContainer.classList.add('hidden');
        threadBtn.textContent = `Show replies (${review.replies_count})`;
        return;
      }
      state.expandedThreads.add(review.id);
      threadBtn.textContent = `Hide replies (${review.replies_count})`;
      repliesContainer.classList.remove('hidden');
      await loadReplies(review.id, repliesContainer);
    };

    if (expanded) loadReplies(review.id, repliesContainer);
    return node;
  }

  async function loadReplies(reviewId, container) {
    const data = await api('social', `api/v1/social/reviews/${reviewId}/replies?skip=0&limit=20`, {
      headers: headers(),
    });
    container.innerHTML = '';
    data.items.forEach((reply) => container.appendChild(buildReviewCard(reply, true)));
  }

  async function loadBooks(q = '') {
    const endpoint = q
      ? `api/v1/books/search?q=${encodeURIComponent(q)}&skip=0&limit=30`
      : 'api/v1/books?skip=0&limit=30';
    const data = await api('book', endpoint);
    state.books = data.items || [];
    renderBookList(state.books);
  }

  async function selectBook(isbn) {
    state.selectedIsbn = isbn;
    state.expandedThreads.clear();
    els.selectedIsbn.textContent = `ISBN: ${isbn}`;
    await loadReviews();
  }

  async function loadReviews() {
    if (!state.selectedIsbn) return;
    if (!state.token) {
      els.reviews.innerHTML = '<p class="muted">Login required to load reviews.</p>';
      return;
    }

    const data = await api('social', `api/v1/social/books/${state.selectedIsbn}/reviews?skip=0&limit=20`, {
      headers: headers(),
    });
    els.reviews.innerHTML = '';
    data.items.forEach((review) => els.reviews.appendChild(buildReviewCard(review)));
  }

  els.loginForm.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await login(els.username.value.trim(), els.password.value);
      setStatus(els.authStatus, `Logged in as ${els.username.value.trim()}`);
      await loadReviews();
    } catch (err) {
      setStatus(els.authStatus, err.message, true);
    }
  };

  els.bookSearch.oninput = () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      loadBooks(els.bookSearch.value).catch((err) => setStatus(els.authStatus, err.message, true));
    }, 250);
  };

  (async function init() {
    if (state.token) setStatus(els.authStatus, 'Token loaded from local storage');
    try {
      await loadBooks();
      if (state.books.length) await selectBook(state.books[0].isbn);
    } catch (err) {
      setStatus(els.authStatus, `Failed to load reviews page: ${err.message}`, true);
    }
  })();
})();

