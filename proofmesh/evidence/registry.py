from proofmesh.evidence.calculator import calculate
from proofmesh.evidence.documents import read_context_document
from proofmesh.evidence.fetch import fetch_url
from proofmesh.evidence.search import web_search


def list_capabilities(settings) -> dict:
    return {"models": {
                "openai_compatible": {"supported": True, "configured": bool(settings.openai_api_key)},
                "ollama": {"supported": True, "configured": bool(settings.ollama_base_url)},
                "mock": {"supported": True, "configured": True}},
            "evidence_tools": {"calculate": True, "fetch_url": True,
                "web_search": settings.search_provider == "brave" and bool(settings.search_api_key),
                "read_context_document": bool(settings.document_root)},
            "notes": ["Secrets are loaded from environment and never returned."]}


__all__ = ["calculate", "fetch_url", "list_capabilities", "read_context_document", "web_search"]
