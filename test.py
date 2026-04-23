# save as discover_routes.py in project root
import asyncio
import aiohttp
import json

SERVICES = {
    "auth": 8001,
    "user": 8002,
    "follow": 8003,
    "social": 8004,
    "rag": 8005,
    "recommendation": 8006,
    "book": 8007,
}

async def discover():
    async with aiohttp.ClientSession() as session:
        for name, port in SERVICES.items():
            url = f"http://localhost:{port}/openapi.json"
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        print(f"\n{'='*50}")
                        print(f"📡 {name.upper()} (:{port})")
                        print(f"{'='*50}")
                        for path, methods in sorted(data.get("paths", {}).items()):
                            method_list = [m.upper() for m in methods.keys() if m != "parameters"]
                            print(f"  {path:<40} {', '.join(method_list)}")
                    else:
                        print(f"\n❌ {name} (:{port}) - HTTP {resp.status}")
            except Exception as e:
                print(f"\n💥 {name} (:{port}) - {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(discover())