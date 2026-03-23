const state = {
  token: localStorage.getItem('bookbox_token') || '',
  selectedIsbn: null,
  books: [],
  allBooks: [],
  searchQuery: '',
  filterField: 'all',
  shelves: [],
  expandedThreads: new Set(),
};

let searchTimer = null;

const els = {
  authStatus: document.getElementById('auth-status'),
  loginForm: document.getElementById('login-form'),
  username: document.getElementById('username'),
  password: document.getElementById('password'),
  refreshBooks: document.getElementById('refresh-books'),
  booksGrid: document.getElementById('books-grid'),
  bookSearch: document.getElementById('book-search'),
  bookFilter: document.getElementById('book-filter'),
  selectedIsbn: document.getElementById('selected-isbn'),
  likeBook: document.getElementById('like-book'),
  rating: document.getElementById('rating'),
  rateBook: document.getElementById('rate-book'),
  reviewTitle: document.getElementById('review-title'),
  reviewContent: document.getElementById('review-content'),
  submitReview: document.getElementById('submit-review'),
  stats: document.getElementById('book-stats'),
  reviews: document.getElementById('reviews'),
  reviewTemplate: document.getElementById('review-template'),
  shelfName: document.getElementById('shelf-name'),
  shelfVisibility: document.getElementById('shelf-visibility'),
  createShelf: document.getElementById('create-shelf'),
  shelvesList: document.getElementById('shelves-list'),
  shelfPick: document.getElementById('shelf-pick'),
  addToShelf: document.getElementById('add-to-shelf'),
  removeFromShelf: document.getElementById('remove-from-shelf'),
};

function headers(json = false) {
  const h = {};
  if (json) h['Content-Type'] = 'application/json';
  if (state.token) h.Authorization = `Bearer ${state.token}`;
  return h;
}

function assertLoggedIn() {
  if (!state.token) {
    throw new Error('Login required for this action');
  }
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

function setAuthStatus(message, isError = false) {
  els.authStatus.textContent = message;
  els.authStatus.style.color = isError ? 'var(--danger)' : 'var(--muted)';
}

async function login(username, password) {
  const data = await api('auth', 'api/v1/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  state.token = data.access_token;
  localStorage.setItem('bookbox_token', state.token);
  setAuthStatus(`Logged in as ${username}`);
}

function applyClientBookFilter(items) {
  const q = state.searchQuery.trim().toLowerCase();
  if (!q) return items;

  return items.filter((book) => {
    const byTitle = String(book.title || '').toLowerCase().includes(q);
    const byAuthor = String(book.author_name || '').toLowerCase().includes(q);
    const byYear = String(book.year || '').includes(q);
    const byIsbn = String(book.isbn || '').toLowerCase().includes(q);

    if (state.filterField === 'title') return byTitle;
    if (state.filterField === 'author') return byAuthor;
    if (state.filterField === 'year') return byYear;
    return byTitle || byAuthor || byYear || byIsbn;
  });
}

function renderBooks() {
  els.booksGrid.innerHTML = '';
  if (!state.books.length) {
    els.booksGrid.innerHTML = '<p class="muted">No books found.</p>';
    return;
  }

  state.books.forEach((book) => {
    const card = document.createElement('article');
    card.className = 'card';
    if (state.selectedIsbn === book.isbn) card.classList.add('selected');
    card.innerHTML = `
      <strong>${book.title}</strong>
      <p class="muted">${book.author_name || 'Unknown author'}</p>
      <p class="muted">${book.year} · ${book.isbn}</p>
    `;
    card.onclick = () => selectBook(book.isbn);
    els.booksGrid.appendChild(card);
  });
}

function renderStats(stats) {
  els.stats.innerHTML = `
    <div class="stat"><div class="muted">Likes</div><strong>${stats.likes_count}</strong></div>
    <div class="stat"><div class="muted">Ratings</div><strong>${stats.ratings_count}</strong></div>
    <div class="stat"><div class="muted">Avg</div><strong>${stats.avg_rating ?? '-'}</strong></div>
  `;
}

function renderShelves() {
  els.shelvesList.innerHTML = '';
  els.shelfPick.innerHTML = '';

  if (!state.shelves.length) {
    els.shelvesList.innerHTML = '<p class="muted">No shelves yet.</p>';
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No shelves';
    els.shelfPick.appendChild(opt);
    return;
  }

  state.shelves.forEach((shelf) => {
    const row = document.createElement('div');
    row.className = 'shelf-item';
    row.innerHTML = `<strong>${shelf.name}</strong><span class="muted">${shelf.visibility}</span>`;
    els.shelvesList.appendChild(row);

    const opt = document.createElement('option');
    opt.value = String(shelf.id);
    opt.textContent = `${shelf.name} (${shelf.visibility})`;
    els.shelfPick.appendChild(opt);
  });
}

async function loadShelves() {
  if (!state.token) {
    state.shelves = [];
    renderShelves();
    return;
  }

  const items = await api('social', 'api/v1/social/shelves/me?skip=0&limit=50', {
    headers: headers(),
  });
  state.shelves = items || [];
  renderShelves();
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
      await api('social', `api/v1/social/reviews/${review.id}/likes`, {
        method: 'POST',
        headers: headers(),
      });
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
  } else {
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

    if (expanded) {
      loadReplies(review.id, repliesContainer);
    }
  }

  return node;
}

async function loadReplies(reviewId, container) {
  try {
    const data = await api('social', `api/v1/social/reviews/${reviewId}/replies?skip=0&limit=20`, {
      headers: headers(),
    });
    container.innerHTML = '';
    data.items.forEach((reply) => container.appendChild(buildReviewCard(reply, true)));
  } catch (err) {
    container.innerHTML = `<p class="muted">${err.message}</p>`;
  }
}

async function loadBooks() {
  const q = state.searchQuery.trim();
  const endpoint = q
    ? `api/v1/books/search?q=${encodeURIComponent(q)}&skip=0&limit=50`
    : 'api/v1/books?skip=0&limit=50';
  const data = await api('book', endpoint);
  state.allBooks = data.items || [];
  state.books = applyClientBookFilter(state.allBooks);
  renderBooks();
}

async function loadReviews() {
  if (!state.selectedIsbn) return;
  if (!state.token) {
    els.reviews.innerHTML = '<p class="muted">Login required to read reviews.</p>';
    return;
  }
  try {
    const data = await api('social', `api/v1/social/books/${state.selectedIsbn}/reviews?skip=0&limit=20`, {
      headers: headers(),
    });
    els.reviews.innerHTML = '';
    data.items.forEach((review) => els.reviews.appendChild(buildReviewCard(review)));
  } catch (err) {
    els.reviews.innerHTML = `<p class="muted">${err.message}</p>`;
  }
}

async function loadStats() {
  if (!state.selectedIsbn) return;
  if (!state.token) {
    els.stats.innerHTML = '<p class="muted">Login required to view social stats.</p>';
    return;
  }
  try {
    const data = await api('social', `api/v1/social/books/${state.selectedIsbn}/stats`, {
      headers: headers(),
    });
    renderStats(data);
  } catch (err) {
    els.stats.innerHTML = `<p class="muted">${err.message}</p>`;
  }
}

async function selectBook(isbn) {
  state.selectedIsbn = isbn;
  state.expandedThreads.clear();
  els.selectedIsbn.textContent = `ISBN: ${isbn}`;
  renderBooks();
  await Promise.all([loadStats(), loadReviews()]);
}

els.loginForm.onsubmit = async (e) => {
  e.preventDefault();
  try {
    await login(els.username.value.trim(), els.password.value);
    await loadShelves();
    if (state.selectedIsbn) await Promise.all([loadStats(), loadReviews()]);
  } catch (err) {
    setAuthStatus(err.message, true);
  }
};

els.refreshBooks.onclick = loadBooks;

els.bookSearch.oninput = () => {
  state.searchQuery = els.bookSearch.value;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    loadBooks().catch((err) => setAuthStatus(`Book search failed: ${err.message}`, true));
  }, 250);
};

els.bookFilter.onchange = () => {
  state.filterField = els.bookFilter.value;
  state.books = applyClientBookFilter(state.allBooks);
  renderBooks();
};

els.createShelf.onclick = async () => {
  try {
    assertLoggedIn();
    if (!els.shelfName.value.trim()) throw new Error('Shelf name is required');
    await api('social', 'api/v1/social/shelves', {
      method: 'POST',
      headers: headers(true),
      body: JSON.stringify({
        name: els.shelfName.value.trim(),
        visibility: els.shelfVisibility.value,
      }),
    });
    els.shelfName.value = '';
    await loadShelves();
  } catch (err) {
    alert(err.message);
  }
};

els.addToShelf.onclick = async () => {
  try {
    assertLoggedIn();
    if (!state.selectedIsbn) throw new Error('Select a book first');
    const shelfId = els.shelfPick.value;
    if (!shelfId) throw new Error('Select a shelf first');
    await api('social', `api/v1/social/shelves/${shelfId}/items`, {
      method: 'POST',
      headers: headers(true),
      body: JSON.stringify({ isbn: state.selectedIsbn, position: 1 }),
    });
    setAuthStatus('Book added to shelf');
  } catch (err) {
    alert(err.message);
  }
};

els.removeFromShelf.onclick = async () => {
  try {
    assertLoggedIn();
    if (!state.selectedIsbn) throw new Error('Select a book first');
    const shelfId = els.shelfPick.value;
    if (!shelfId) throw new Error('Select a shelf first');
    await api('social', `api/v1/social/shelves/${shelfId}/items/${encodeURIComponent(state.selectedIsbn)}`, {
      method: 'DELETE',
      headers: headers(),
    });
    setAuthStatus('Book removed from shelf');
  } catch (err) {
    alert(err.message);
  }
};

els.likeBook.onclick = async () => {
  try {
    assertLoggedIn();
    if (!state.selectedIsbn) throw new Error('Select a book first');
    await api('social', `api/v1/social/likes/${state.selectedIsbn}`, {
      method: 'POST',
      headers: headers(),
    });
    await loadStats();
  } catch (err) {
    alert(err.message);
  }
};

els.rateBook.onclick = async () => {
  try {
    assertLoggedIn();
    if (!state.selectedIsbn) throw new Error('Select a book first');
    await api('social', `api/v1/social/ratings/${state.selectedIsbn}`, {
      method: 'PUT',
      headers: headers(true),
      body: JSON.stringify({ rating: Number(els.rating.value) }),
    });
    await loadStats();
  } catch (err) {
    alert(err.message);
  }
};

els.submitReview.onclick = async () => {
  try {
    assertLoggedIn();
    if (!state.selectedIsbn) throw new Error('Select a book first');
    await api('social', 'api/v1/social/reviews', {
      method: 'POST',
      headers: headers(true),
      body: JSON.stringify({
        isbn: state.selectedIsbn,
        title: els.reviewTitle.value,
        content: els.reviewContent.value,
      }),
    });
    els.reviewTitle.value = '';
    els.reviewContent.value = '';
    await Promise.all([loadStats(), loadReviews()]);
  } catch (err) {
    alert(err.message);
  }
};

(async function init() {
  if (state.token) {
    setAuthStatus('Token loaded from local storage');
  }
  try {
    await loadBooks();
    if (state.books.length) await selectBook(state.books[0].isbn);
    await loadShelves();
  } catch (err) {
    setAuthStatus(`Failed to load app data: ${err.message}`, true);
  }
})();

