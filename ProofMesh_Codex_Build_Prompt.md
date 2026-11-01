# Codex Build Brief: ProofMesh (Team NexEra)

You are the senior software architect and implementation engineer for **ProofMesh**, an evidence-first, dynamic multi-agent network. Build a working, testable backend that can be connected to an external assistant through MCP. Do not build a toy demo that only simulates agents with hard-coded outputs.

## Product objective

Given one user prompt, ProofMesh must:
1. Use a lead planner to decompose the task into a dependency-aware task graph.
2. Create task-specific specialist workers at runtime. Do not hard-code domain agents such as finance, travel, or healthcare agents.
3. Run independent work orders concurrently, with a bounded worker pool and a global resource budget.
4. Allow any agent to message any other agent through an internal peer-to-peer event bus.
5. Persist run state, decisions, messages, artifacts, claims, evidence, and review findings in a shared task ledger.
6. Require factual claims in the final answer to carry evidence and a verification status.
7. Run independent review for unsupported claims and contradictions; return only the failing claim IDs to the responsible worker for repair.
8. Expose the workflow as an MCP server so another assistant can call it.
9. Offer a single-agent baseline and a blind baseline-versus-network comparison using the same prompt and selected model configuration.

## Required technology choices

- Python 3.12
- FastAPI for health/configuration endpoints where useful
- Official Python MCP SDK for MCP tools; prefer Streamable HTTP for hosted judging
- asyncio for concurrent workers and an in-process event bus in the first release
- Pydantic v2 for all agent, task, claim, evidence, message, and tool schemas
- SQLAlchemy 2.x for persistence; SQLite locally, PostgreSQL in deployment
- Model-provider abstraction with an OpenAI-compatible adapter and Ollama adapter first
- httpx for retrieval; create a provider interface for web search rather than tying orchestration to one vendor
- pytest and pytest-asyncio for tests

Do not add Redis, Kafka, Kubernetes, a vector database, or a frontend to the MVP. Keep interfaces ready for later scaling, but do not make those dependencies necessary to run the project. An optional dashboard can be added only after the MCP workflow works end to end.

## Runtime architecture

`MCP Gateway -> Run Orchestrator -> Lead Planner -> Dynamic Task Graph -> Async Worker Pool <-> Peer Message Bus -> Shared Task Ledger -> Evidence / Consistency Reviewer -> Targeted Repair -> Final Synthesizer`

The baseline runner is a separate mode that calls one agent using the same model profile and evidence tools. The benchmark runner invokes both modes and randomises the output order.

## Core data contracts

Create Pydantic models at minimum for:

### ModelProfile
- `provider`: `openai_compatible` or `ollama`
- `model`: provider model identifier
- `base_url`: optional provider endpoint
- `temperature`: default 0.2
- `max_output_tokens`: bounded integer
- Never include API key values in this object. Load secrets from environment variables or a secret manager.

### WorkOrder
- `task_id`, `run_id`, `assigned_agent_id`
- `objective`
- `deliverable_schema`
- `dependencies: list[str]`
- `acceptance_criteria: list[str]`
- `allowed_capabilities: list[str]`
- `evidence_required: bool`
- `status`: queued, running, completed, blocked, failed

### AgentMessage
- `message_id`, `run_id`, `sender_agent_id`, `recipient_agent_id`
- `message_type`: request, evidence, finding, challenge, clarification, status
- `related_task_ids: list[str]`
- `related_claim_ids: list[str]`
- `payload` as validated structured data
- `created_at`

### Claim
- `claim_id`, `run_id`, `owner_agent_id`
- `text`
- `claim_type`: fact, calculation, inference, recommendation
- `evidence_ids: list[str]`
- `subject`, `predicate`, `value`, `scope`, `time_context` (nullable fields for contradiction matching)
- `verification_status`: pending, supported, disputed, unsupported, qualified
- `review_notes: list[str]`

### Evidence
- `evidence_id`, `run_id`, `source_type`: web, document, tool_result, calculation, user_context
- `source_uri` (nullable)
- `title` (nullable)
- `excerpt` or `content_digest`
- `retrieved_at`
- `source_metadata` (JSON)
- For calculations, store the expression, inputs, and result instead of inventing a URL.

### ReviewFinding
- `finding_id`, `run_id`, `reviewer_agent_id`
- `claim_id`
- `finding_type`: missing_evidence, weak_support, contradiction, stale_source, unsupported_number, scope_mismatch
- `explanation`
- `required_action`
- `status`: open, repaired, unresolved, rejected

## Orchestration requirements

1. The lead planner returns a validated `TaskPlan` containing a short rationale, work orders, dependencies, and required capabilities.
2. Validate the task graph before execution. Reject unknown dependencies and cycles. Run only tasks whose dependencies are complete.
3. Use `asyncio.Semaphore` to cap parallel work. Use per-agent timeouts and a single run-level token/cost budget.
4. Give every agent a minimal context package: original prompt, relevant task dependencies, shared decisions, and assigned artifacts. Do not dump the entire conversation into every worker.
5. Agent messages must be routed by recipient ID through the event bus. Persist all messages. Any agent may message any other agent within the same run.
6. Workers must return structured artifacts and atomic claims. Do not accept free-form output as the only stored result.
7. The reviewer must check claim-to-evidence support and compare claims for conflicts. Use structured field matching first; use the configured LLM for semantic review when needed.
8. Send targeted review findings to the owning worker. Limit the default process to two repair rounds.
9. Final answer policy: a factual claim with no supporting evidence must never be labelled supported. Preserve it as qualified/unverified or omit it. Surface unresolved contradictions explicitly.
10. Final output must include a concise answer, important caveats, claim IDs, and an evidence index that can be retrieved through MCP.

## Evidence capabilities

Create a capability registry with at least:
- `web_search(query)` using a provider interface and an environment-configured search provider
- `fetch_url(url)` with safe URL validation and content extraction
- `read_context_document(document_ref)` for user-provided context that the server can access
- `calculate(expression, inputs)` using a safe, constrained evaluator; do not use Python `eval`

If a capability is unavailable, report it as unavailable. Never fabricate search results, source URLs, quotations, or tool outputs. Record retrieval timestamps. Keep source excerpts short but sufficient to support the linked claim.

## MCP tools to expose

Implement typed MCP tools with input validation and documented output schemas:

1. `proofmesh_run_task(prompt, model_profile, max_agents=5, review_rounds=2, budget_tokens, context_refs=[])` -> `{run_id, status}`
2. `proofmesh_get_run(run_id)` -> status, current stage, active agents, completed tasks, token usage, and timestamps
3. `proofmesh_get_result(run_id)` -> final answer, caveats, claim IDs, and benchmark/run metadata
4. `proofmesh_get_evidence(run_id, claim_id)` -> linked evidence, excerpts, source metadata, and review history
5. `proofmesh_compare_blind(prompt, model_profile, budget_tokens)` -> two anonymised answers with randomised X/Y ordering and a private server-side mapping retained for audit
6. `proofmesh_list_capabilities()` -> configured model adapters and available evidence tools; never return secrets

Use a stable naming prefix and include clear descriptions so an unfamiliar MCP client can discover and call the tools.

## Fair comparison rules

For the primary experiment, baseline and network must use:
- the exact same user prompt;
- the same configured model identifier and provider;
- the same retrieval/tool capability set;
- the same temperature and relevant generation settings;
- a clearly declared, comparable total token budget policy.

Record network overhead honestly: number of model calls, tokens, latency, and estimated provider cost. Randomise whether the baseline or network is Response X. Do not include labels such as “multi-agent” or “baseline” in the text shown to blind graders. Keep the mapping only in the benchmark record.

For the David-versus-Goliath demonstration, allow a small local open-source model for the network and a top-tier hosted model for the single agent, but label it as a separate experiment. Do not mix its results with the same-model comparison.

## Persistence tables

At minimum create tables for:
- `runs`
- `agents`
- `work_orders`
- `agent_messages`
- `artifacts`
- `claims`
- `evidence`
- `review_findings`
- `benchmark_pairs`
- `usage_events`

Use `run_id` as the tenant/isolation boundary. Add indexes for `run_id`, status fields, and claim/evidence relationships. Do not expose records from another run.

## Suggested repository structure

```text
proofmesh/
  app/
    main.py
    config.py
    mcp_server.py
    api/
      health.py
    core/
      orchestrator.py
      planner.py
      scheduler.py
      message_bus.py
      budget.py
      synthesizer.py
    agents/
      base.py
      worker.py
      reviewer.py
      prompts.py
    models/
      provider_base.py
      openai_compatible.py
      ollama.py
      factory.py
    evidence/
      registry.py
      search.py
      fetch.py
      documents.py
      calculator.py
      claim_validator.py
      contradiction.py
    benchmark/
      baseline.py
      blind_runner.py
      metrics.py
    schemas/
      tasks.py
      agents.py
      claims.py
      evidence.py
      messages.py
      mcp.py
    storage/
      database.py
      models.py
      repository.py
  tests/
    test_task_graph.py
    test_message_bus.py
    test_parallel_execution.py
    test_claim_evidence_gate.py
    test_contradiction_review.py
    test_targeted_repair.py
    test_blind_randomisation.py
    test_run_isolation.py
  .env.example
  pyproject.toml
  README.md
```

You may adjust the exact layout if a cleaner architecture is justified, but preserve the module boundaries.

## Required tests and acceptance criteria

- A task graph with independent tasks runs them concurrently; dependent tasks do not start early.
- A cyclic or invalid task graph is rejected before workers start.
- Agent A can message Agent B and Agent C in the same run; messages are persisted and isolated by run ID.
- A worker can submit a factual claim linked to a retrieved source and the reviewer can mark it supported only when the excerpt is relevant.
- A claim with no evidence cannot pass the final evidence gate as supported.
- Two conflicting claims are flagged; if repair fails, the final answer surfaces the conflict or excludes the disputed assertion.
- A targeted repair updates only the relevant claim/artifact and preserves unrelated completed work.
- An unavailable search tool never results in fabricated sources.
- Baseline and network modes use the requested same model profile in the same-model experiment.
- Blind output ordering is randomised; the identity mapping is not returned with the two answers.
- API keys are absent from database rows, logs, prompts, messages, MCP outputs, and exception traces.
- `pytest` passes, the server starts from documented commands, and an external MCP client can call `proofmesh.run_task` end to end.

## Build sequence

Work in small, runnable commits. Do not write the entire codebase in one pass.

1. Scaffold configuration, schemas, database, model adapter, health check, and MCP server. Add a mock model adapter for deterministic tests.
2. Implement baseline execution and MCP smoke test.
3. Implement task planning, graph validation, scheduler, worker runtime, and event bus.
4. Add task ledger persistence and structured artifacts.
5. Add evidence capabilities, claim ledger, and evidence gate.
6. Add reviewer, contradiction checks, targeted repair, and bounded retry handling.
7. Add blind comparison, metrics, sealed-prompt runner, security checks, and complete README.

At the end of each step, run tests and fix failures before moving on. Use mock adapters in CI so tests do not require paid API keys. Keep real provider integration behind environment configuration. Include a sample `.env.example`, but never include real credentials.

## Definition of done

A developer can clone the repository, install dependencies, configure either an OpenAI-compatible endpoint or Ollama, start the MCP server, connect an external assistant, submit an arbitrary multi-faceted prompt, inspect its run, retrieve the final answer and supporting evidence, and execute a blind baseline/network comparison. The implementation must clearly expose unresolved uncertainty rather than inventing support.
