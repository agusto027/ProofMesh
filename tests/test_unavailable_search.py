import pytest

from proofmesh.evidence.search import web_search


@pytest.mark.asyncio
async def test_missing_search_provider_is_reported_not_fabricated(monkeypatch):
    monkeypatch.setenv("PROOFMESH_SEARCH_PROVIDER", "none")
    monkeypatch.delenv("PROOFMESH_SEARCH_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="unavailable"):
        await web_search("a query")
