(() => {
  const { state, headers, assertLoggedIn, api, login, setStatus } = window.Bookbox;

  const els = {
    authStatus: document.getElementById('auth-status'),
    loginForm: document.getElementById('login-form'),
    username: document.getElementById('username'),
    password: document.getElementById('password'),
    shelfName: document.getElementById('shelf-name'),
    shelfVisibility: document.getElementById('shelf-visibility'),
    createShelf: document.getElementById('create-shelf'),
    shelvesList: document.getElementById('shelves-list'),
    shelfPick: document.getElementById('shelf-pick'),
    refreshShelfBooks: document.getElementById('refresh-shelf-books'),
    bookSearch: document.getElementById('book-search'),
    booksGrid: document.getElementById('books-grid'),
    selectedIsbn: document.getElementById('selected-isbn'),
    addToShelf: document.getElementById('add-to-shelf'),
    removeFromShelf: document.getElementById('remove-from-shelf'),
    shelfBooksList: document.getElementById('shelf-books-list'),
    shelfBooksSort: document.getElementById('shelf-books-sort'),
    shelfBooksSortDir: document.getElementById('shelf-books-sort-dir'),
  };

  let searchTimer = null;
  let shelfBooks = [];
  let shelfSortBy = 'position';
  let shelfSortDir = 'asc';

  function renderShelves(shelves) {
    els.shelvesList.innerHTML = '';
    els.shelfPick.innerHTML = '';

    if (!shelves.length) {
      els.shelvesList.innerHTML = '<p class="muted">No shelves yet.</p>';
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = 'No shelves';
      els.shelfPick.appendChild(empty);
      els.shelfBooksList.innerHTML = '<p class="muted">No shelf selected.</p>';
      return;
    }

    shelves.forEach((shelf) => {
      const row = document.createElement('div');
      row.className = 'shelf-item';
      row.innerHTML = `<strong>${shelf.name}</strong><span class="muted">${shelf.visibility}</span>`;
      els.shelvesList.appendChild(row);

      const option = document.createElement('option');
      option.value = String(shelf.id);
      option.textContent = `${shelf.name} (${shelf.visibility})`;
      els.shelfPick.appendChild(option);
    });

    if (els.shelfPick.value) {
      loadShelfBooks().catch((err) => setStatus(els.authStatus, err.message, true));
    }
  }

  function sortShelfBooks(items) {
    const copy = [...items];
    copy.sort((a, b) => {
      if (shelfSortBy === 'title') {
        const ta = String(a.title || a.isbn || '').toLowerCase();
        const tb = String(b.title || b.isbn || '').toLowerCase();
        if (ta < tb) return shelfSortDir === 'asc' ? -1 : 1;
        if (ta > tb) return shelfSortDir === 'asc' ? 1 : -1;
        return 0;
      }

      const pa = Number(a.position || 0);
      const pb = Number(b.position || 0);
      if (pa < pb) return shelfSortDir === 'asc' ? -1 : 1;
      if (pa > pb) return shelfSortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }

  function renderShelfBooks(items) {
    els.shelfBooksList.innerHTML = '';
    if (!items.length) {
      els.shelfBooksList.innerHTML = '<p class="muted">Shelf has no books yet.</p>';
      return;
    }

    const sorted = sortShelfBooks(items);
    const table = document.createElement('table');
    table.className = 'shelf-books-table';
    table.innerHTML = `
      <thead>
        <tr>
          <th>Pos</th>
          <th>Title</th>
          <th>Author</th>
          <th>Year</th>
          <th>ISBN</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;

    const tbody = table.querySelector('tbody');
    sorted.forEach((item) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${item.position}</td>
        <td>${item.title || item.isbn}</td>
        <td>${item.author_name || '-'}</td>
        <td>${item.year || '-'}</td>
        <td>${item.isbn}</td>
      `;
      tbody.appendChild(tr);
    });

    els.shelfBooksList.appendChild(table);
  }

  async function loadShelfBooks() {
    assertLoggedIn();
    const shelfId = els.shelfPick.value;
    if (!shelfId) {
      els.shelfBooksList.innerHTML = '<p class="muted">Select a shelf to view books.</p>';
      return;
    }

    const data = await api('social', `api/v1/social/shelves/${shelfId}/books?skip=0&limit=100`, {
      headers: headers(),
    });
    shelfBooks = data.items || [];
    renderShelfBooks(shelfBooks);
  }

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
      card.onclick = () => {
        state.selectedIsbn = book.isbn;
        els.selectedIsbn.textContent = `Selected ISBN: ${book.isbn}`;
        renderBooks(state.books);
      };
      els.booksGrid.appendChild(card);
    });
  }

  async function loadShelves() {
    if (!state.token) {
      renderShelves([]);
      return;
    }

    const items = await api('social', 'api/v1/social/shelves/me?skip=0&limit=50', {
      headers: headers(),
    });
    state.shelves = items || [];
    renderShelves(state.shelves);
  }

  async function loadBooks(q = '') {
    const endpoint = q
      ? `api/v1/books/search?q=${encodeURIComponent(q)}&skip=0&limit=40`
      : 'api/v1/books?skip=0&limit=40';
    const data = await api('book', endpoint);
    state.books = data.items || [];
    renderBooks(state.books);
  }

  els.loginForm.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await login(els.username.value.trim(), els.password.value);
      setStatus(els.authStatus, `Logged in as ${els.username.value.trim()}`);
      await loadShelves();
      await loadShelfBooks();
    } catch (err) {
      setStatus(els.authStatus, err.message, true);
    }
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
      await loadShelfBooks();
    } catch (err) {
      alert(err.message);
    }
  };

  els.addToShelf.onclick = async () => {
    try {
      assertLoggedIn();
      if (!state.selectedIsbn) throw new Error('Select a book first');
      if (!els.shelfPick.value) throw new Error('Select a shelf first');
      await api('social', `api/v1/social/shelves/${els.shelfPick.value}/items`, {
        method: 'POST',
        headers: headers(true),
        body: JSON.stringify({ isbn: state.selectedIsbn, position: 1 }),
      });
      setStatus(els.authStatus, 'Book added to shelf');
      await loadShelfBooks();
    } catch (err) {
      alert(err.message);
    }
  };

  els.removeFromShelf.onclick = async () => {
    try {
      assertLoggedIn();
      if (!state.selectedIsbn) throw new Error('Select a book first');
      if (!els.shelfPick.value) throw new Error('Select a shelf first');
      await api('social', `api/v1/social/shelves/${els.shelfPick.value}/items/${encodeURIComponent(state.selectedIsbn)}`, {
        method: 'DELETE',
        headers: headers(),
      });
      setStatus(els.authStatus, 'Book removed from shelf');
      await loadShelfBooks();
    } catch (err) {
      alert(err.message);
    }
  };

  els.refreshShelfBooks.onclick = () => {
    loadShelfBooks().catch((err) => setStatus(els.authStatus, err.message, true));
  };

  els.shelfPick.onchange = () => {
    loadShelfBooks().catch((err) => setStatus(els.authStatus, err.message, true));
  };

  els.shelfBooksSort.onchange = () => {
    shelfSortBy = els.shelfBooksSort.value;
    renderShelfBooks(shelfBooks);
  };

  els.shelfBooksSortDir.onclick = () => {
    shelfSortDir = shelfSortDir === 'asc' ? 'desc' : 'asc';
    els.shelfBooksSortDir.textContent = shelfSortDir === 'asc' ? 'Asc' : 'Desc';
    renderShelfBooks(shelfBooks);
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
      await Promise.all([loadShelves(), loadBooks()]);
      if (state.books.length) {
        state.selectedIsbn = state.books[0].isbn;
        els.selectedIsbn.textContent = `Selected ISBN: ${state.selectedIsbn}`;
        renderBooks(state.books);
      }
      if (state.token) {
        await loadShelfBooks();
      } else {
        els.shelfBooksList.innerHTML = '<p class="muted">Login to view shelf books.</p>';
      }
    } catch (err) {
      setStatus(els.authStatus, `Failed to load shelves page: ${err.message}`, true);
    }
  })();
})();

