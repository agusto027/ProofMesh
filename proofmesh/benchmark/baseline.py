import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from proofmesh.core.budget import TokenBudget
from proofmesh.evidence.calculator import calculate
from proofmesh.evidence.fetch import fetch_url
from proofmesh.evidence.search import web_search
from proofmesh.models.factory import create_adapter
from proofmesh.schemas.core import ModelProfile
from proofmesh.storage.database import Session
from proofmesh.storage.models import EvidenceRow, RunRow, UsageEventRow


async def run_baseline(prompt: str, profile: ModelProfile, budget_tokens: int) -> dict:
    run_id = str(uuid4())
    budget = TokenBudget(budget_tokens)
    adapter = create_adapter(profile)
    async with Session() as session:
        session.add(RunRow(run_id=run_id, prompt=prompt, status="running", stage="baseline",
            model_profile=profile.model_dump(exclude_none=True), token_budget=budget_tokens,
            token_usage=0, metadata_json={"mode": "baseline", "provider": profile.provider,
                                         "model": profile.model}))
        await session.commit()
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": "Answer the user's request directly as one assistant. You may request evidence using the same capabilities as ProofMesh. Never invent sources. Return only JSON with keys answer, claims, evidence_requests."},
        {"role": "user", "content": prompt}]
    model_calls = 0
    evidence_rows = []

    async def call():
        nonlocal model_calls
        result = await adapter.complete(messages)
        budget.charge(result.input_tokens + result.output_tokens)
        model_calls += 1
        async with Session() as session:
            session.add(UsageEventRow(usage_id=str(uuid4()), run_id=run_id, agent_id="baseline",
                purpose="baseline", input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                latency_ms=result.latency_ms, estimated_cost=None))
            await session.commit()
        return result.text

    raw = await call()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = {"answer": raw, "evidence_requests": []}
    for request in decoded.get("evidence_requests", []):
        try:
            kind = request.get("type")
            if kind == "search":
                entries = await web_search(str(request.get("query", "")))
                evidence_rows.extend({"source_type": "web", "source_uri": row["url"],
                    "title": row["title"], "excerpt": row["excerpt"]} for row in entries)
            elif kind == "fetch":
                entry = await fetch_url(str(request.get("url", "")))
                evidence_rows.append({"source_type": "web", "source_uri": entry["url"],
                    "title": entry["title"], "excerpt": entry["excerpt"]})
            elif kind == "calculate":
                entry = calculate(str(request.get("expression", "")), request.get("inputs", {}))
                evidence_rows.append({"source_type": "calculation", "title": "Safe calculation",
                    "excerpt": f"{entry['expression']} with {entry['inputs']} = {entry['result']}",
                    "source_metadata": entry})
        except (RuntimeError, ValueError, ArithmeticError, httpx.HTTPError, OSError, KeyError, TypeError):
            # An unavailable capability creates no evidence row.
            continue
    async with Session() as session:
        for entry in evidence_rows:
            session.add(EvidenceRow(evidence_id=str(uuid4()), run_id=run_id,
                source_type=entry["source_type"], source_uri=entry.get("source_uri"),
                title=entry.get("title"), excerpt=(entry.get("excerpt") or "")[:1200],
                content_digest=None, retrieved_at=datetime.now(UTC),
                source_metadata=entry.get("source_metadata", {})))
        await session.commit()
    if evidence_rows:
        messages.extend([
            {"role": "assistant", "content": raw},
            {"role": "user", "content": json.dumps({"retrieved_evidence": evidence_rows,
                "instruction": "Now answer the original prompt. Use only the evidence shown and qualify uncertainty."})}])
        raw = await call()
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = {"answer": raw}
    answer = str(decoded.get("answer", raw))
    async with Session() as session:
        run = await session.get(RunRow, run_id)
        run.status, run.stage, run.answer = "completed", "complete", answer
        run.token_usage = budget.used
        await session.commit()
    return {"run_id": run_id, "answer": answer, "token_usage": budget.used,
            "model_calls": model_calls, "latency_ms": int((time.perf_counter() - started) * 1000)}
