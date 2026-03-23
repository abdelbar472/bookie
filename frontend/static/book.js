(() => {
  const { api, setStatus } = window.Bookbox;

  const els = {
    status: document.getElementById('status'),
    output: document.getElementById('output'),
    query: document.getElementById('book-query'),
    isbn: document.getElementById('isbn'),
    authorId: document.getElementById('author-id'),
    searchBtn: document.getElementById('search-btn'),
    listBtn: document.getElementById('list-btn'),
    byIsbnBtn: document.getElementById('book-by-isbn-btn'),
    authorsBtn: document.getElementById('authors-btn'),
    authorByIdBtn: document.getElementById('author-by-id-btn'),
    publishersBtn: document.getElementById('publishers-btn'),
  };

  const show = (obj) => { els.output.textContent = JSON.stringify(obj, null, 2); };

  els.searchBtn.onclick = async () => {
    try {
      const q = els.query.value.trim() || 'a';
      const res = await api('book', `api/v1/books/search?q=${encodeURIComponent(q)}&skip=0&limit=20`);
      show(res);
      setStatus(els.status, 'Search results loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.listBtn.onclick = async () => {
    try {
      const res = await api('book', 'api/v1/books?skip=0&limit=20');
      show(res);
      setStatus(els.status, 'Book list loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.byIsbnBtn.onclick = async () => {
    try {
      const res = await api('book', `api/v1/books/${encodeURIComponent(els.isbn.value.trim())}`);
      show(res);
      setStatus(els.status, 'Book loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.authorsBtn.onclick = async () => {
    try {
      const res = await api('book', 'api/v1/authors?skip=0&limit=20');
      show(res);
      setStatus(els.status, 'Authors loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.authorByIdBtn.onclick = async () => {
    try {
      const id = Number(els.authorId.value || 0);
      const res = await api('book', `api/v1/authors/${id}`);
      show(res);
      setStatus(els.status, 'Author loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };

  els.publishersBtn.onclick = async () => {
    try {
      const res = await api('book', 'api/v1/publishers?skip=0&limit=20');
      show(res);
      setStatus(els.status, 'Publishers loaded');
    } catch (err) { setStatus(els.status, err.message, true); }
  };
})();

