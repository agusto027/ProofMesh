# ProofMesh
<<<<<<< HEAD

ProofMesh is an evidence-first orchestration service with a Python MCP server. It creates a task graph for each request, runs task-specific workers concurrently, records the run ledger in SQLite or PostgreSQL, checks claim evidence, and exposes run/result/evidence retrieval tools.

## Requirements

- Python 3.12+
- An OpenAI-compatible endpoint or Ollama for real model calls (the deterministic `mock` adapter is available for local checks)
- Optional Brave Search API key for web search

## Install and start

```powershell
uv sync --extra dev
Copy-Item .env.example .env
# Set provider secrets in .env or the process environment.
uv run proofmesh
```

The FastAPI health endpoint is `GET http://localhost:8000/health`; MCP Streamable HTTP is mounted at `http://localhost:8000/mcp`. To use Ollama, set `PROOFMESH_OLLAMA_BASE_URL` and pass a profile such as `{"provider":"ollama","model":"qwen2.5:7b"}`. For OpenAI-compatible providers, configure `PROOFMESH_OPENAI_BASE_URL` and `PROOFMESH_OPENAI_API_KEY`, then pass `{"provider":"openai_compatible","model":"your-model"}`. API keys are read from the environment and are never part of a model profile or output.

SQLite is the default. For PostgreSQL, install `uv sync --extra postgres` and set `PROOFMESH_DATABASE_URL=postgresql+asyncpg://...`. `PROOFMESH_MAX_BUDGET_TOKENS` caps the per-run budget accepted by the service (default 50,000).

## MCP tools

- `proofmesh_run_task`: execute a prompt, using `model_profile`, `max_agents`, `review_rounds`, `budget_tokens`, and optional `context_refs`.
- `proofmesh_get_run`: inspect stage, status, task completion, token usage, and timestamps.
- `proofmesh_get_result`: retrieve the answer, caveats, claims, evidence index, and metadata.
- `proofmesh_get_evidence`: retrieve a claim's linked excerpts and review history, scoped to its run.
- `proofmesh_compare_blind`: run the single-agent baseline and network with the same prompt/profile/budget; returns anonymized X/Y answers. The mapping and metrics are retained in `benchmark_pairs`.
- `proofmesh_list_capabilities`: inspect available providers and evidence tools without exposing secrets.

## Evidence tools and safety

`calculate` accepts numeric arithmetic only and does not call Python `eval`. `fetch_url` allows public HTTP(S) hosts, blocks private/local addresses, and does not follow redirects. `web_search` is unavailable unless `PROOFMESH_SEARCH_PROVIDER=brave` and `PROOFMESH_SEARCH_API_KEY` are configured. A missing search provider produces an explicit unavailable capability record; it never creates synthetic citations. Context references are accepted in the request contract; this initial release records them but does not read arbitrary server paths. Integrators should pass authorized documents through a future context adapter rather than grant arbitrary file access.

Claims without relevant linked evidence cannot be marked supported. Review can flag unsupported claims and structured contradictions and can request up to two targeted repairs. Unresolved claims remain qualified or disputed and appear in caveats. Evidence excerpts are capped at 1,200 characters. Provider usage is recorded; estimated cost remains null unless a provider-specific pricing adapter is configured.

## Tests

```powershell
uv run pytest
```

Tests use local schemas and deterministic mock components; no paid API key is needed.
=======
A complete backend multi agent system
>>>>>>> e35f3b0feec78af6d0d45a65b28dd3e61e47edae
