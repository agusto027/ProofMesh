import os

import httpx


async def web_search(query: str) -> list[dict]:
    provider = os.getenv("PROOFMESH_SEARCH_PROVIDER", "none").lower()
    if provider != "brave" or not os.getenv("PROOFMESH_SEARCH_API_KEY"):
        raise RuntimeError("Web search is unavailable: configure PROOFMESH_SEARCH_PROVIDER=brave and its API key.")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 5},
            headers={"X-Subscription-Token": os.environ["PROOFMESH_SEARCH_API_KEY"],
                     "Accept": "application/json"})
        response.raise_for_status()
    rows = response.json().get("web", {}).get("results", [])
    return [{"title": row.get("title", ""), "url": row.get("url", ""),
             "excerpt": row.get("description", "")[:800]} for row in rows]
