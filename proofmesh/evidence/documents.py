from hashlib import sha256
from pathlib import Path

from bs4 import BeautifulSoup


def read_context_document(document_ref: str, document_root: str | None) -> dict:
    if not document_root:
        raise RuntimeError("Document access is unavailable: PROOFMESH_DOCUMENT_ROOT is not configured.")
    root = Path(document_root).expanduser().resolve(strict=True)
    candidate = (root / document_ref).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise ValueError("Document reference is outside the configured document root.")
    candidate = candidate.resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise ValueError("Document reference is outside the configured document root.")
    if candidate.suffix.lower() not in {".txt", ".md", ".html", ".htm"}:
        raise ValueError("Only text, Markdown, and HTML context documents are supported.")
    content = candidate.read_text(encoding="utf-8", errors="replace")
    if candidate.suffix.lower() in {".html", ".htm"}:
        content = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    return {"title": candidate.name, "source_uri": str(candidate), "excerpt": content[:1200],
            "content_digest": sha256(content.encode("utf-8")).hexdigest()}
