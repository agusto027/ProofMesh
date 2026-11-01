import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


def _validate_public_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only absolute HTTP(S) URLs are accepted.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in URLs are not allowed.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        addresses = []
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private and local network URLs are blocked.")


async def fetch_url(url: str) -> dict:
    _validate_public_url(url)
    async with httpx.AsyncClient(follow_redirects=False, timeout=20) as client:
        response = await client.get(url, headers={"User-Agent": "ProofMesh/0.1 evidence-fetch"})
        response.raise_for_status()
    if "text/html" not in response.headers.get("content-type", ""):
        raise ValueError("Only HTML pages can be extracted.")
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return {"url": str(response.url), "title": soup.title.get_text(" ", strip=True) if soup.title else None,
            "excerpt": " ".join(soup.get_text(" ", strip=True).split())[:1200]}
