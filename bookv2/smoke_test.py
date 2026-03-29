from bookv2.external_clients import build_author_from_google_and_wiki, normalize_google_book


def run() -> None:
    sample_book = {
        "id": "test-book-1",
        "volumeInfo": {
            "title": "Animal Farm",
            "authors": ["George Orwell"],
            "description": "Political satire novel.",
            "categories": ["Fiction"],
            "language": "en",
            "publishedDate": "1945",
            "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780451526342"}],
        },
    }
    sample_wiki = {
        "title": "George Orwell",
        "bio": "English novelist and essayist.",
        "lang": "en",
        "url": "https://en.wikipedia.org/wiki/George_Orwell",
    }

    normalized_book = normalize_google_book(sample_book)
    normalized_author = build_author_from_google_and_wiki("George Orwell", sample_wiki, categories=["Fiction"])

    assert normalized_book["book_id"] == "9780451526342"
    assert normalized_book["isbn"] == "9780451526342"
    assert normalized_author["author_id"] == "name:george-orwell"
    assert normalized_author["name"] == "George Orwell"
    assert "Bio:" in normalized_author["style_text"]

    print("bookv2 smoke test passed")


if __name__ == "__main__":
    run()

