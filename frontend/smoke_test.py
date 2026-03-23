import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frontend.app import app


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        for page in ["/", "/auth", "/user", "/follow", "/book", "/social", "/reviews", "/shelves"]:
            resp = await client.get(page)
            assert resp.status_code == 200, f"Expected 200 for {page}, got {resp.status_code}"

        home = await client.get("/")
        assert "id=\"book-search\"" in home.text, "Home search input missing"

        auth = await client.get("/auth")
        assert "id=\"register-btn\"" in auth.text, "Auth register button missing"

        user = await client.get("/user")
        assert "id=\"me-btn\"" in user.text, "User /me button missing"

        follow = await client.get("/follow")
        assert "id=\"follow-btn\"" in follow.text, "Follow action button missing"

        book = await client.get("/book")
        assert "id=\"search-btn\"" in book.text, "Book search button missing"

        social = await client.get("/social")
        assert "id=\"like-btn\"" in social.text, "Social like button missing"

        reviews = await client.get("/reviews")
        assert "thread-toggle" in reviews.text, "Reviews thread toggle missing"

        shelves = await client.get("/shelves")
        assert "id=\"create-shelf\"" in shelves.text, "Shelves create button missing"

    print("frontend smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())

