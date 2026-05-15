import requests
import time
import json
from datetime import datetime
from typing import Dict

# ==================== CONFIG ====================
BASE_URL = "http://127.0.0.1:8001"  # Change to 8007 if you use old port
OUTPUT_FILE = "v4_test_results.json"
LOG_FILE = "v4_test_summary.log"

# ==================== TEST CASES ====================
TEST_CASES = {
    "authors": [
        "Naguib Mahfouz", "Alaa Al Aswany", "Ahmed Khaled Tawfik",
        "William Shakespeare", "George Orwell", "Haruki Murakami"
    ],
    "books": [
        "1984", "Dune", "The Alchemist", "ألف ليلة وليلة", "زقاق المدق",
        "Harry Potter", "One Hundred Years of Solitude"
    ],
    "series": [
        "Harry Potter", "Dune", "The Lord of the Rings",
        "أغنية الجليد والنار", "Foundation"
    ]
}


def test_endpoint(url: str, method: str = "GET", json_data=None) -> Dict:
    start = time.time()
    try:
        if method == "GET":
            resp = requests.get(url, timeout=30)
        else:
            resp = requests.post(url, json=json_data, timeout=30)

        duration = round(time.time() - start, 3)

        result = {
            "url": url,
            "status_code": resp.status_code,
            "duration_seconds": duration,
        }

        if resp.status_code == 200:
            data = resp.json()
            result["success"] = True
            # For authors, show total_works; for series, show books in series; for author books, show total
            if data.get("results") and len(data["results"]) > 0:
                profile = data["results"][0]
                if "stats" in profile and "total_works" in profile["stats"]:
                    items_count = profile["stats"]["total_works"]
                elif "books" in profile:
                    items_count = len(profile["books"])
                elif "total_books" in profile:
                    items_count = profile["total_books"]
                else:
                    items_count = len(data.get("results", []))
            elif "books" in data:
                items_count = len(data["books"])
            elif "total" in data:
                items_count = data["total"]
            else:
                items_count = len(data.get("results", []))
            result["items_count"] = items_count
            result["response"] = data
        else:
            result["success"] = False
            result["error"] = resp.text[:300]

        return result

    except Exception as e:
        return {"url": url, "status_code": "error", "error": str(e), "duration_seconds": round(time.time() - start, 3)}


def run_v4_test():
    print("🚀 Starting Book Service V4 Test")
    print(f"Base URL: {BASE_URL}")
    print("=" * 90)

    all_results = []
    summary = []

    # Health Check
    health = test_endpoint(f"{BASE_URL}/api/v3/health")
    print(f"Health Check → {health['status_code']} ({health['duration_seconds']}s)")
    all_results.append({"test": "Health", **health})

    # Test Authors
    print("\n👤 Testing Authors:")
    for name in TEST_CASES["authors"]:
        url = f"{BASE_URL}/api/v3/authors/search?name={requests.utils.quote(name)}"
        result = test_endpoint(url)
        all_results.append({"test": f"Author: {name}", **result})

        status = "✅" if result.get("success") else "❌"
        count = result.get("items_count", 0)
        print(f"   {status} {name:<25} | Books: {count} | Time: {result['duration_seconds']:.2f}s")
        summary.append(f"{status} Author: {name}")

    # Test Books
    print("\n📖 Testing Books:")
    for q in TEST_CASES["books"]:
        url = f"{BASE_URL}/api/v3/books/search?q={requests.utils.quote(q)}"
        result = test_endpoint(url)
        all_results.append({"test": f"Book: {q}", **result})

        status = "✅" if result.get("success") else "❌"
        count = result.get("items_count", 0)
        print(f"   {status} {q:<25} | Results: {count} | Time: {result['duration_seconds']:.2f}s")
        summary.append(f"{status} Book: {q}")

    # Test Series
    print("\n📚 Testing Series:")
    for name in TEST_CASES["series"]:
        url = f"{BASE_URL}/api/v3/series/search?name={requests.utils.quote(name)}"
        result = test_endpoint(url)
        all_results.append({"test": f"Series: {name}", **result})

        status = "✅" if result.get("success") else "❌"
        count = result.get("items_count", 0)
        print(f"   {status} {name:<25} | Books: {count} | Time: {result['duration_seconds']:.2f}s")
        summary.append(f"{status} Series: {name}")

    # Save Results
    final_report = {
        "test_run_at": datetime.now().isoformat(),
        "service": "Book Service V4",
        "total_tests": len(all_results),
        "successful": sum(1 for r in all_results if r.get("success")),
        "results": all_results
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(summary))

    print("\n" + "=" * 90)
    print("🎉 V4 TEST COMPLETED!")
    print(f"📁 Results saved to: {OUTPUT_FILE}")
    print(f"Success Rate: {final_report['successful']}/{final_report['total_tests']}")


if __name__ == "__main__":
    run_v4_test()