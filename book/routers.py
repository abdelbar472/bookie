import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .auth import get_current_user_id
from .schemas import (
    AwardCreate, AwardResponse,
    PublisherCreate, PublisherResponse,
    AuthorCreate, AuthorResponse, AuthorDetailResponse, AuthorAwardCreate,
    BookCreate, BookResponse, BookListResponse, BookSummary,
)
from .services import (
    create_award, get_award_by_id, list_awards,
    create_publisher, get_publisher_by_name, list_publishers,
    create_author, get_author_by_id, list_authors,
    assign_award_to_author, get_author_awards, get_author_books,
    create_book, get_book_by_isbn, list_books, search_books, enrich_book,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "healthy", "service": "book-service"}


# ── Publishers (internal write, public read) ───────────────────────────────────

@router.post(
    "/internal/publishers",
    response_model=PublisherResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Internal] Add a publisher",
)
async def add_publisher(
    data: PublisherCreate,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        pub = await create_publisher(session, data.name, data.location, data.year_founded)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return pub


@router.get("/publishers", response_model=list[PublisherResponse])
async def list_publishers_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    items, _ = await list_publishers(session, skip=skip, limit=limit)
    return items


@router.get("/publishers/{name}", response_model=PublisherResponse)
async def get_publisher_route(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    pub = await get_publisher_by_name(session, name)
    if not pub:
        raise HTTPException(status_code=404, detail="Publisher not found")
    return pub


# ── Awards (internal write, public read) ───────────────────────────────────────

@router.post(
    "/internal/awards",
    response_model=AwardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Internal] Add an award",
)
async def add_award(
    data: AwardCreate,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    award = await create_award(session, data.name, data.year, data.category, data.country)
    return award


@router.get("/awards", response_model=list[AwardResponse])
async def list_awards_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    items, _ = await list_awards(session, skip=skip, limit=limit)
    return items


@router.get("/awards/{award_id}", response_model=AwardResponse)
async def get_award_route(
    award_id: int,
    session: AsyncSession = Depends(get_session),
):
    award = await get_award_by_id(session, award_id)
    if not award:
        raise HTTPException(status_code=404, detail="Award not found")
    return award


# ── Authors (internal write, public read) ─────────────────────────────────────

@router.post(
    "/internal/authors",
    response_model=AuthorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Internal] Add an author",
)
async def add_author(
    data: AuthorCreate,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    author = await create_author(
        session, data.name, data.country,
        data.year_born, data.year_died, data.type_of_writer,
    )
    return author


@router.post(
    "/internal/authors/awards",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="[Internal] Assign an award to an author",
)
async def assign_award(
    data: AuthorAwardCreate,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        await assign_award_to_author(session, data.author_id, data.award_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"author_id": data.author_id, "award_id": data.award_id, "assigned": True}


@router.get("/authors", response_model=list[AuthorResponse])
async def list_authors_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    items, _ = await list_authors(session, skip=skip, limit=limit)
    return items


@router.get("/authors/{author_id}", response_model=AuthorDetailResponse)
async def get_author_route(
    author_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    author = await get_author_by_id(session, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    books, _ = await get_author_books(session, author_id, skip=skip, limit=limit)
    awards = await get_author_awards(session, author_id)
    return AuthorDetailResponse(
        id=author.id,
        name=author.name,
        country=author.country,
        year_born=author.year_born,
        year_died=author.year_died,
        type_of_writer=author.type_of_writer,
        books=[BookSummary(isbn=b.isbn, title=b.title, year=b.year) for b in books],
        awards=[AwardResponse(id=a.id, name=a.name, year=a.year, category=a.category, country=a.country) for a in awards],
    )


# ── Books (internal write, public read) ────────────────────────────────────────

@router.post(
    "/internal/books",
    response_model=BookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Internal] Add a book",
)
async def add_book(
    data: BookCreate,
    _: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        book = await create_book(
            session, data.isbn, data.title, data.year,
            data.author_id, data.publisher_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    enriched = await enrich_book(session, book)
    return BookResponse(**enriched)


@router.get("/books", response_model=BookListResponse)
async def list_books_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    books, total = await list_books(session, skip=skip, limit=limit)
    items = [BookResponse(**await enrich_book(session, b)) for b in books]
    return BookListResponse(items=items, total=total)


@router.get("/books/search", response_model=BookListResponse)
async def search_books_route(
    q: str = Query(..., min_length=1, description="Title or ISBN keyword"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    books, total = await search_books(session, q, skip=skip, limit=limit)
    items = [BookResponse(**await enrich_book(session, b)) for b in books]
    return BookListResponse(items=items, total=total)


@router.get("/books/{isbn}", response_model=BookResponse)
async def get_book_route(
    isbn: str,
    session: AsyncSession = Depends(get_session),
):
    book = await get_book_by_isbn(session, isbn)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    enriched = await enrich_book(session, book)
    return BookResponse(**enriched)


@router.get("/authors/{author_id}/books", response_model=BookListResponse)
async def get_books_by_author(
    author_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    author = await get_author_by_id(session, author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found")
    books, total = await get_author_books(session, author_id, skip=skip, limit=limit)
    items = [BookResponse(**await enrich_book(session, b)) for b in books]
    return BookListResponse(items=items, total=total)

