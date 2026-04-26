import json
import time
import requests
from datetime import datetime
from typing import List, Dict

# ==================== CONFIG ====================
BASE_URL = "http://127.0.0.1:8007"
OUTPUT_FILE = "v3_full_test_results.json"
LOG_FILE = "v3_test_summary.log"

# ==================== BIG MIXED TEST CASES ====================
TEST_CASES = {
    "authors": [
        # Arabic & Egyptian
        "Naguib Mahfouz", "Alaa Al Aswany", "Tawfiq al-Hakim", "Yusuf Idris",
        "Ahlam Mosteghanemi", "Khalil Gibran", "Mahmoud Darwish", "Nawal El Saadawi",
        "Ahmed Khaled Tawfik", "Sonallah Ibrahim", "Khaled Khalifa", "Adania Shibli",
        "Taha Hussein", "Ihsan Abdel Quddous", "Gamal El Ghitani", "Ghassan Kanafani",
        "Emile Habibi", "Hanan al-Shaykh", "Leila Aboulela", "Hoda Barakat",
        "Bensalem Himmich", "Ibrahim Nasrallah",

        # English & American
        "William Shakespeare", "Jane Austen", "George Orwell", "Ernest Hemingway",
        "Toni Morrison", "Chimamanda Ngozi Adichie", "J.K. Rowling",

        # International
        "Haruki Murakami", "Gabriel García Márquez", "Franz Kafka", "Victor Hugo",
        "Leo Tolstoy", "Marcel Proust", "Isabel Allende", "Orhan Pamuk",
        "Rabindranath Tagore", "Pablo Neruda"
    ],

    "books": [
        # English
        "1984", "Dune", "The Alchemist", "Pride and Prejudice", "Harry Potter",
        "The Great Gatsby", "To Kill a Mockingbird",

        # Arabic
        "كتاب الرعب", "ألف ليلة وليلة", "عائد إلى حيفا", "الأيام", "اللص والكلاب",
        "زقاق المدق",

        # Other languages
        "El Alquimista", "Le Petit Prince", "1Q84", "One Hundred Years of Solitude",
        "Crime and Punishment", "Norwegian Wood"
    ],

    "series": [
        # Famous series
        "Harry Potter", "Dune", "The Lord of the Rings", "Game of Thrones",
        "أغنية الجليد والنار", "The Wheel of Time", "Foundation",

        # Arabic / Regional
        "سلسلة أرض الخيال", "مغامرات سندباد", "سلسلة الخيال العلمي"
    ]
}

# ==================== TEST FUNCTION ====================
def test_endpoint(session: requests.Session, method: str, url: str, json_data=None) -> Dict:
    start = time.time()
    try:
        if method == "GET":
            resp = session.get(url, timeout=30)
        else:
            resp = session.post(url, json=json_data, timeout=30)

        duration = round(time.time() - start, 3)

        result = {
            "method": method,
            "url": url,
            "status_code": resp.status_code,
            "duration_seconds": duration,
            "timestamp": datetime.now().isoformat(),
        }

        if resp.status_code == 200:
            data = resp.json()
            result["full_response"] = data
            result["summary"] = {"items_count": len(data.get("results", data.get("books", [])))}
        else:
            result["error"] = resp.text[:400]

        return result

    except Exception as e:
        return {
            "method": method,
            "url": url,
            "status_code": "error",
            "duration_seconds": round(time.time() - start, 3),
            "error": str(e)
        }


# ==================== MAIN TEST ====================
def run_comprehensive_test():
    print("🚀 Starting BIG V3 API TEST - Mixed Languages + Books + Authors + Series")
    print(f"Base URL: {BASE_URL}/api/v3")
    print("=" * 110)

    session = requests.Session()
    all_results = []
    summary_lines = []

    # 1. Health Check
    print("\n🔍 1. Health Check")
    health = test_endpoint(session, "GET", f"{BASE_URL}/api/v3/health")
    all_results.append({"test": "Health Check", **health})
    print(f"   Health → {health['status_code']} ({health['duration_seconds']}s)")

    # 2. Authors (Mixed languages)
    print("\n👤 2. Testing Authors (Arabic + English + International)")
    for name in TEST_CASES["authors"]:
        url = f"{BASE_URL}/api/v3/authors/search?name={requests.utils.quote(name)}"
        result = test_endpoint(session, "GET", url)
        all_results.append({"test": f"Author: {name}", **result})

        status = "✅" if result["status_code"] == 200 else "❌"
        count = result.get("summary", {}).get("items_count", 0)
        print(f"   {status} {name:<28} | Books: {count:2d} | Time: {result['duration_seconds']:.2f}s")
        summary_lines.append(f"{status} Author: {name:<28} | Books: {count}")

        time.sleep(0.9)

    # 3. Books Search (Mixed languages)
    print("\n📖 3. Testing Books Search (Mixed Languages)")
    for q in TEST_CASES["books"]:
        url = f"{BASE_URL}/api/v3/books/search?q={requests.utils.quote(q)}&limit=10"
        result = test_endpoint(session, "GET", url)
        all_results.append({"test": f"Book: {q}", **result})

        status = "✅" if result["status_code"] == 200 else "❌"
        count = result.get("summary", {}).get("items_count", 0)
        print(f"   {status} {q:<28} | Results: {count:2d} | Time: {result['duration_seconds']:.2f}s")
        summary_lines.append(f"{status} Book: {q:<28} | Results: {count}")

        time.sleep(0.9)

    # 4. Series Search
    print("\n📚 4. Testing Series Search")
    for name in TEST_CASES["series"]:
        url = f"{BASE_URL}/api/v3/series/search?name={requests.utils.quote(name)}"
        result = test_endpoint(session, "GET", url)
        all_results.append({"test": f"Series: {name}", **result})

        status = "✅" if result["status_code"] == 200 else "❌"
        count = result.get("summary", {}).get("items_count", 0)
        print(f"   {status} {name:<28} | Books: {count:2d} | Time: {result['duration_seconds']:.2f}s")
        summary_lines.append(f"{status} Series: {name:<28} | Books: {count}")

        time.sleep(0.9)

    # 5. Unified POST Search
    print("\n🔄 5. Testing Unified POST /search")
    unified_cases = [
        {"query": "Naguib Mahfouz", "type": "author"},
        {"query": "1984", "type": "book"},
        {"query": "Dune", "type": "series"},
        {"query": "ألف ليلة وليلة", "type": "book"},
    ]
    for case in unified_cases:
        payload = {**case, "limit": 8}
        url = f"{BASE_URL}/api/v3/search"
        result = test_endpoint(session, "POST", url, payload)
        all_results.append({"test": f"Unified {case['type']}: {case['query']}", **result})
        print(f"   Unified {case['type'].upper()} → {result['status_code']} ({result['duration_seconds']}s)")

    # ==================== SAVE RESULTS ====================
    final_report = {
        "test_run_at": datetime.now().isoformat(),
        "service": "Book Service V3",
        "total_tests": len(all_results),
        "successful": sum(1 for r in all_results if r.get("status_code") == 200),
        "results": all_results
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Book Service V3 - BIG MIXED TEST REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 110 + "\n\n")
        f.write("\n".join(summary_lines))

    print("\n" + "=" * 110)
    print("🎉 BIG V3 TEST COMPLETED SUCCESSFULLY!")
    print(f"📁 Full detailed results  → {OUTPUT_FILE}")
    print(f"📝 Summary log           → {LOG_FILE}")
    print(f"Success Rate: {final_report['successful']}/{final_report['total_tests']}")


if __name__ == "__main__":
    try:
        requests.get(f"{BASE_URL}/api/v3/health", timeout=5)
        run_comprehensive_test()
    except:
        print("❌ Cannot connect to the server!")
        print(f"Please run your V3 service first:")
        print("   python -m book_service_v3.main")