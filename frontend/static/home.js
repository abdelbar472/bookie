(() => {
  const { state, headers, assertLoggedIn, api, login, setStatus } = window.Bookbox;

  const els = {
    authStatus: document.getElementById('auth-status'),
    loginForm: document.getElementById('login-form'),
    username: document.getElementById('username'),
    password: document.getElementById('password'),
    refreshBooks: document.getElementById('refresh-books'),
    bookSearch: document.getElementById('book-search'),
    booksGrid: document.getElementById('books-grid'),
    selectedIsbn: document.getElementById('selected-isbn'),
    likeBook: document.getElementById('like-book'),
    rating: document.getElementById('rating'),
    rateBook: document.getElementById('rate-book'),
    reviewTitle: document.getElementById('review-title'),
    reviewContent: document.getElementById('review-content'),
    submitReview: document.getElementById('submit-review'),
    stats: document.getElementById('book-stats'),
  };

  let searchTimer = null;

  function renderBooks(items) {
    els.booksGrid.innerHTML = '';
    if (!items.length) {
      els.booksGrid.innerHTML = '<p class="muted">No books found.</p>';
      return;
    }

    items.forEach((book) => {
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

  async function loadBooks(q = '') {
    const endpoint = q
      ? `api/v1/books/search?q=${encodeURIComponent(q)}&skip=0&limit=50`
      : 'api/v1/books?skip=0&limit=50';
    const data = await api('book', endpoint);
    state.books = data.items || [];
    renderBooks(state.books);
  }

  async function loadStats() {
    if (!state.selectedIsbn || !state.token) {
      els.stats.innerHTML = '<p class="muted">Login to view social stats.</p>';
      return;
    }
    const data = await api('social', `api/v1/social/books/${state.selectedIsbn}/stats`, { headers: headers() });
    renderStats(data);
  }

  async function selectBook(isbn) {
    state.selectedIsbn = isbn;
    els.selectedIsbn.textContent = `ISBN: ${isbn}`;
    renderBooks(state.books);
    await loadStats();
  }

  els.loginForm.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await login(els.username.value.trim(), els.password.value);
      setStatus(els.authStatus, `Logged in as ${els.username.value.trim()}`);
      await loadStats();
    } catch (err) {
      setStatus(els.authStatus, err.message, true);
    }
  };

  els.refreshBooks.onclick = () => loadBooks(els.bookSearch.value).catch((err) => setStatus(els.authStatus, err.message, true));

  els.bookSearch.oninput = () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      loadBooks(els.bookSearch.value).catch((err) => setStatus(els.authStatus, err.message, true));
    }, 250);
  };

  els.likeBook.onclick = async () => {
    try {
      assertLoggedIn();
      if (!state.selectedIsbn) throw new Error('Select a book first');
      await api('social', `api/v1/social/likes/${state.selectedIsbn}`, { method: 'POST', headers: headers() });
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
      await loadStats();
    } catch (err) {
      alert(err.message);
    }
  };

  (async function init() {
    if (state.token) setStatus(els.authStatus, 'Token loaded from local storage');
    try {
      await loadBooks();
      if (state.books.length) await selectBook(state.books[0].isbn);
    } catch (err) {
      setStatus(els.authStatus, `Failed to load books: ${err.message}`, true);
    }
  })();
})();

