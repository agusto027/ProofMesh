import asyncio
import json
import logging
import time
from collections import defaultdict
from uuid import uuid4

import httpx
from pydantic import ValidationError
from sqlalchemy import delete, select, update

from proofmesh.app.config import get_settings
from proofmesh.core.budget import TokenBudget
from proofmesh.core.message_bus import MessageBus
from proofmesh.core.scheduler import execute_ready
from proofmesh.core.task_graph import normalize_tasks
from proofmesh.evidence.calculator import calculate
from proofmesh.evidence.documents import read_context_document
from proofmesh.evidence.fetch import fetch_url
from proofmesh.evidence.search import web_search
from proofmesh.models.factory import create_adapter
from proofmesh.schemas.core import (
    AgentMessage,
    Claim,
    Evidence,
    RunRequest,
    RunResult,
    TaskPlan,
)
from proofmesh.storage.database import Session
from proofmesh.storage.models import (
    AgentMessageRow,
    AgentRow,
    ArtifactRow,
    ClaimEvidenceRow,
    ClaimRow,
    EvidenceRow,
    ReviewFindingRow,
    RunRow,
    UsageEventRow,
    WorkOrderRow,
)

log = logging.getLogger("proofmesh")


def _json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        left, right = text.find("{"), text.rfind("}")
        if left < 0 or right <= left:
            raise ValueError("Model returned no JSON object.")
        value = json.loads(text[left:right + 1])
    if not isinstance(value, dict):
        raise TypeError("Model output must be a JSON object.")
    return value


class Orchestrator:
    def __init__(self):
        self.active: dict[str, set[str]] = defaultdict(set)
        self.metrics: dict[str, dict[str, int]] = defaultdict(lambda: {"model_calls": 0, "latency_ms": 0})

    async def _call(self, adapter, budget, run_id, purpose, messages, agent_id=None):
        result = await adapter.complete(messages)
        self.metrics[run_id]["model_calls"] += 1
        self.metrics[run_id]["latency_ms"] += result.latency_ms
        budget.charge(result.input_tokens + result.output_tokens)
        async with Session() as session:
            session.add(UsageEventRow(usage_id=str(uuid4()), run_id=run_id, agent_id=agent_id,
                purpose=purpose, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                latency_ms=result.latency_ms, estimated_cost=None))
            amount = result.input_tokens + result.output_tokens
            await session.execute(update(RunRow).where(RunRow.run_id == run_id).values(
                token_usage=RunRow.token_usage + amount))
            await session.commit()
        return result.text

    async def run(self, request: RunRequest) -> RunResult:
        if request.budget_tokens > get_settings().max_budget_tokens:
            raise ValueError("Requested token budget exceeds PROOFMESH_MAX_BUDGET_TOKENS.")
        run_id = str(uuid4())
        adapter = create_adapter(request.model_profile)
        budget = TokenBudget(request.budget_tokens)
        async with Session() as session:
            session.add(RunRow(run_id=run_id, prompt=request.prompt, status="running", stage="planning",
                model_profile=request.model_profile.model_dump(exclude_none=True), token_budget=request.budget_tokens,
                token_usage=0, metadata_json={"mode": "network", "provider": request.model_profile.provider,
                                             "model": request.model_profile.model}))
            await session.commit()
        try:
            context_packages = []
            for document_ref in request.context_refs:
                try:
                    document = read_context_document(document_ref, get_settings().document_root)
                    context_packages.append(document)
                    async with Session() as session:
                        session.add(EvidenceRow(evidence_id=str(uuid4()), run_id=run_id,
                            source_type="user_context", source_uri=document["source_uri"],
                            title=document["title"], excerpt=document["excerpt"],
                            content_digest=document["content_digest"], source_metadata={}))
                        await session.commit()
                except (RuntimeError, ValueError, OSError) as exc:
                    async with Session() as session:
                        run = await session.get(RunRow, run_id)
                        metadata = dict(run.metadata_json or {})
                        metadata.setdefault("unavailable_capabilities", []).append({
                            "capability": "read_context_document", "error_type": type(exc).__name__})
                        run.metadata_json = metadata
                        await session.commit()
            planner_text = await self._call(adapter, budget, run_id, "planning", [
                {"role": "system", "content": "You are a lead planner. Decompose the prompt into a small dependency-aware task plan. Return only JSON with keys rationale, required_capabilities, work_orders. Each work order: task_id, objective, deliverable_schema, dependencies (task_ids), acceptance_criteria, allowed_capabilities, evidence_required. Use 1-5 tasks; create independent tasks where useful."},
                {"role": "user", "content": f"TaskPlan for: {request.prompt}"}], "planner")
            plan_data = _json(planner_text)
            raw_orders = plan_data.get("work_orders", [])
            if len(raw_orders) > 50:
                raise ValueError("Planner returned more than 50 work orders.")
            # Dependencies to omitted tasks invalidate the plan and fail before workers execute.
            for item in raw_orders:
                item["run_id"] = run_id
                item["assigned_agent_id"] = "pending"
            plan = TaskPlan(rationale=plan_data.get("rationale", ""), work_orders=raw_orders,
                            required_capabilities=plan_data.get("required_capabilities", []))
            tasks = normalize_tasks(plan, run_id, request.max_agents)
            async with Session() as session:
                run = await session.get(RunRow, run_id)
                run.metadata_json = {**run.metadata_json, "planner_rationale": plan.rationale,
                                     "required_capabilities": plan.required_capabilities}
                for i in range(min(request.max_agents, max(1, len(tasks)))):
                    agent_id = f"{run_id}:agent-{i + 1}"
                    session.add(AgentRow(agent_id=agent_id, run_id=run_id, role="worker",
                        specialty=tasks[i].objective[:160] if i < len(tasks) else "dynamic specialist",
                        status="idle"))
                session.add(AgentRow(agent_id=f"{run_id}:reviewer-1", run_id=run_id,
                    role="reviewer", specialty="claim evidence and contradiction review", status="idle"))
                for task in tasks:
                    session.add(WorkOrderRow(task_id=task.task_id, run_id=run_id,
                        assigned_agent_id=task.assigned_agent_id, objective=task.objective,
                        payload=task.model_dump(mode="json"), status="queued"))
                run = await session.get(RunRow, run_id)
                run.stage = "executing"
                await session.commit()

            async def persist_message(message):
                async with Session() as session:
                    session.add(AgentMessageRow(message_id=message.message_id, run_id=message.run_id,
                        sender_agent_id=message.sender_agent_id, recipient_agent_id=message.recipient_agent_id,
                        message_type=message.message_type, payload=message.model_dump(mode="json"),
                        created_at=message.created_at))
                    await session.commit()
            bus = MessageBus(persist_message)
            completed: set[str] = set()
            outputs: dict[str, dict] = {}
            semaphore = asyncio.Semaphore(request.max_agents)
            deadline = time.monotonic() + 600
            while len(completed) < len(tasks):
                async def execute(task):
                    self.active[run_id].add(task.assigned_agent_id)
                    async with Session() as session:
                        row = await session.get(WorkOrderRow, task.task_id)
                        row.status = "running"
                        agent = await session.get(AgentRow, task.assigned_agent_id)
                        if agent:
                            agent.status = "running"
                        await session.commit()
                    context = {"original_prompt": request.prompt, "objective": task.objective,
                               "dependencies": {d: outputs[d] for d in task.dependencies},
                               "context_documents": context_packages}
                    worker_text = await asyncio.wait_for(self._call(adapter, budget, run_id,
                        "worker", [{"role": "system", "content": (
                            "You are a task-specific ProofMesh worker. Return only JSON with keys summary, claims, evidence_requests. "
                            "claims is a list of objects with text, claim_type, subject, predicate, value, scope, time_context. "
                            "Never invent sources. evidence_requests is a list of {type: search|fetch|calculate, query|url|expression, inputs}. "
                            "If no evidence tool can support a factual assertion, mark its claim_type inference or recommendation. "
                            "You may include peer_messages with recipient_agent_id, message_type, and structured payload.")},
                            {"role": "user", "content": json.dumps(context)}], task.assigned_agent_id),
                        timeout=get_settings().worker_timeout_seconds)
                    output = _json(worker_text)
                    output["task_id"] = task.task_id
                    for peer in output.get("peer_messages", []):
                        recipient = peer.get("recipient_agent_id")
                        if recipient in ({f"{run_id}:agent-{i + 1}" for i in range(request.max_agents)}
                                         | {f"{run_id}:reviewer-1"}):
                            message = AgentMessage(run_id=run_id, sender_agent_id=task.assigned_agent_id,
                                recipient_agent_id=recipient,
                                message_type=peer.get("message_type", "status"),
                                related_task_ids=[task.task_id], payload=peer.get("payload", {}))
                            await bus.send(message)
                    async with Session() as session:
                        session.add(ArtifactRow(artifact_id=str(uuid4()), run_id=run_id,
                            task_id=task.task_id, agent_id=task.assigned_agent_id, content=output))
                        row = await session.get(WorkOrderRow, task.task_id)
                        row.status = "completed"
                        agent = await session.get(AgentRow, task.assigned_agent_id)
                        if agent:
                            agent.status = "completed"
                        await session.commit()
                    self.active[run_id].discard(task.assigned_agent_id)
                    return task, output
                results = await execute_ready(tasks, completed, execute, semaphore)
                for task, output in results:
                    completed.add(task.task_id)
                    outputs[task.task_id] = output
                    for request_evidence in output.get("evidence_requests", []):
                        await self._collect_evidence(run_id, task, request_evidence)
                    await self._store_claims(run_id, task, output.get("claims", []))
                if time.monotonic() > deadline:
                    raise TimeoutError("Run exceeded its wall clock limit.")

            async with Session() as session:
                run = await session.get(RunRow, run_id)
                run.stage = "reviewing"
                await session.commit()
            await self._review(run_id, request.review_rounds, outputs, adapter, budget, bus)
            async with Session() as session:
                run = await session.get(RunRow, run_id)
                run.stage = "finalizing"
                await session.commit()
            result = await self._synthesize(run_id, request.prompt, outputs, adapter, budget)
            async with Session() as session:
                run = await session.get(RunRow, run_id)
                run.status, run.stage, run.answer = "completed", "complete", result.answer
                await session.commit()
            return result
        except Exception as exc:
            # Persist a safe error class only; provider exception messages may contain request details.
            log.warning("Run %s failed (%s)", run_id, type(exc).__name__)
            async with Session() as session:
                run = await session.get(RunRow, run_id)
                if run:
                    run.status, run.stage = "failed", "failed"
                    run.metadata_json = {**run.metadata_json, "error_type": type(exc).__name__}
                    await session.commit()
                for order in (await session.scalars(select(WorkOrderRow).where(
                    WorkOrderRow.run_id == run_id, WorkOrderRow.status == "running"))).all():
                    order.status = "failed"
                for agent in (await session.scalars(select(AgentRow).where(
                    AgentRow.run_id == run_id, AgentRow.status == "running"))).all():
                    agent.status = "failed"
                await session.commit()
            self.active.pop(run_id, None)
            raise

    async def _collect_evidence(self, run_id, task, item):
        try:
            kind = item.get("type")
            if kind == "search":
                found = await web_search(str(item.get("query", "")))
                rows = [Evidence(run_id=run_id, source_type="web", source_uri=x["url"],
                                 title=x["title"], excerpt=x["excerpt"]) for x in found]
            elif kind == "fetch":
                data = await fetch_url(str(item.get("url", "")))
                rows = [Evidence(run_id=run_id, source_type="web", source_uri=data["url"],
                                 title=data["title"], excerpt=data["excerpt"])]
            elif kind == "calculate":
                data = calculate(str(item.get("expression", "")), item.get("inputs", {}))
                rows = [Evidence(run_id=run_id, source_type="calculation", title="Safe calculation",
                    excerpt=f"{data['expression']} with {data['inputs']} = {data['result']}",
                    source_metadata=data)]
            else:
                return
        except (RuntimeError, ValueError, ArithmeticError, httpx.HTTPError, OSError, KeyError, TypeError, ValidationError) as exc:
            # Tool unavailability is explicit in run metadata and never replaced with fabricated evidence.
            rows = []
            async with Session() as session:
                run = await session.get(RunRow, run_id)
                metadata = dict(run.metadata_json or {})
                metadata.setdefault("unavailable_capabilities", []).append(
                    {"capability": item.get("type", "unknown"), "error_type": type(exc).__name__})
                run.metadata_json = metadata
                await session.commit()
        async with Session() as session:
            for evidence in rows:
                session.add(EvidenceRow(evidence_id=evidence.evidence_id, run_id=run_id,
                    source_type=evidence.source_type, source_uri=evidence.source_uri, title=evidence.title,
                    excerpt=(evidence.excerpt or "")[:1200], content_digest=evidence.content_digest,
                    source_metadata=evidence.source_metadata))
            await session.commit()

    async def _store_claims(self, run_id, task, claims):
        async with Session() as session:
            evidence_rows = (await session.scalars(select(EvidenceRow).where(EvidenceRow.run_id == run_id))).all()
            for raw in claims:
                try:
                    claim = Claim(run_id=run_id, owner_agent_id=task.assigned_agent_id,
                        evidence_ids=raw.get("evidence_ids", []), **{k: raw.get(k) for k in
                        ("text", "claim_type", "subject", "predicate", "value", "scope", "time_context")})
                except ValidationError:
                    continue
                linked = {e.evidence_id: e for e in evidence_rows}
                valid = [eid for eid in claim.evidence_ids if eid in linked]
                if not valid and claim.claim_type in ("fact", "calculation"):
                    valid = [e.evidence_id for e in evidence_rows
                             if (claim.claim_type == "calculation" and e.source_type == "calculation"
                                 and str(e.source_metadata.get("result", "")) in claim.text)
                             or (claim.claim_type == "fact" and self._relevant(claim.text, e.excerpt or ""))]
                claim.evidence_ids = valid
                status = "pending"
                if claim.claim_type == "fact":
                    status = "supported" if any(self._relevant(claim.text, linked[eid].excerpt or "") for eid in valid) else "unsupported"
                elif claim.claim_type == "calculation":
                    status = "supported" if any(linked[eid].source_type == "calculation" for eid in valid) else "qualified"
                else:
                    status = "qualified"
                claim.verification_status = status
                session.add(ClaimRow(claim_id=claim.claim_id, run_id=run_id,
                    owner_agent_id=claim.owner_agent_id, text=claim.text, claim_type=claim.claim_type,
                    evidence_ids=claim.evidence_ids, subject=claim.subject, predicate=claim.predicate,
                    value=claim.value, scope=claim.scope, time_context=claim.time_context,
                    verification_status=status, review_notes=[]))
                for evidence_id in valid:
                    session.add(ClaimEvidenceRow(run_id=run_id, claim_id=claim.claim_id,
                                                 evidence_id=evidence_id))
            await session.commit()

    @staticmethod
    def _relevant(claim, excerpt):
        words = {w.lower().strip(".,!?;:()") for w in claim.split() if len(w) > 3}
        source = {w.lower().strip(".,!?;:()") for w in excerpt.split() if len(w) > 3}
        return bool(words) and len(words & source) / len(words) >= 0.25

    async def _review(self, run_id, rounds, outputs, adapter, budget, bus):
        reviewer = f"{run_id}:reviewer-1"
        async with Session() as session:
            claims_to_check = (await session.scalars(select(ClaimRow).where(
                ClaimRow.run_id == run_id, ClaimRow.claim_type == "fact",
                ClaimRow.verification_status == "supported"))).all()
            evidence_to_check = (await session.scalars(select(EvidenceRow).where(
                EvidenceRow.run_id == run_id))).all()
            evidence_map = {row.evidence_id: {"excerpt": row.excerpt, "source_uri": row.source_uri,
                                               "title": row.title} for row in evidence_to_check}
            review_targets = [(claim.claim_id, claim.text,
                               [evidence_map[eid] for eid in claim.evidence_ids if eid in evidence_map])
                              for claim in claims_to_check]
        for claim_id, claim_text, linked_sources in review_targets:
            if not linked_sources:
                continue
            response = await self._call(adapter, budget, run_id, "evidence_review", [
                {"role": "system", "content": "Independently review whether the supplied excerpts directly support the claim, including subject, scope, and time. Topical similarity is not enough. Return only JSON {verdict: supported|unsupported|qualified, reason: string}. Do not use outside knowledge."},
                {"role": "user", "content": json.dumps({"claim": claim_text, "sources": linked_sources})}], reviewer)
            try:
                verdict = _json(response)
            except (ValueError, TypeError):
                verdict = {"verdict": "qualified", "reason": "Reviewer returned invalid structured output."}
            if verdict.get("verdict") not in ("supported", "unsupported", "qualified"):
                verdict = {"verdict": "qualified", "reason": "Reviewer returned an unknown verdict."}
            if verdict["verdict"] != "supported":
                async with Session() as session:
                    claim = await session.get(ClaimRow, claim_id)
                    claim.verification_status = verdict["verdict"]
                    claim.review_notes = list(claim.review_notes or []) + [str(verdict.get("reason", ""))]
                    await session.commit()
        async with Session() as session:
            reviewer_row = await session.get(AgentRow, reviewer)
            reviewer_row.status = "running"
            claims = (await session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id))).all()
            for claim in claims:
                if claim.claim_type == "fact" and claim.verification_status != "supported":
                    session.add(ReviewFindingRow(finding_id=str(uuid4()), run_id=run_id,
                        reviewer_agent_id=reviewer, claim_id=claim.claim_id,
                        finding_type="missing_evidence" if not claim.evidence_ids else "weak_support",
                        explanation="The claim does not have relevant linked evidence.",
                        required_action="Add relevant evidence or qualify/remove the claim.",
                        status="unresolved" if rounds == 0 else "open"))
                for other in claims:
                    if other.claim_id <= claim.claim_id or not claim.subject or claim.subject != other.subject:
                        continue
                    if claim.predicate == other.predicate and claim.value and other.value and claim.value != other.value:
                        for item in (claim, other):
                            item.verification_status = "disputed"
                            item.review_notes = list(item.review_notes or []) + ["Conflicting values for matching subject and predicate."]
                            session.add(ReviewFindingRow(finding_id=str(uuid4()), run_id=run_id,
                                reviewer_agent_id=reviewer, claim_id=item.claim_id,
                                finding_type="contradiction", explanation="Claims disagree on the same subject and predicate.",
                                required_action="Resolve the conflict or preserve it as an explicit caveat.",
                                status="unresolved" if rounds == 0 else "open"))
            await session.commit()

        # Targeted repairs only touch claims attached to open findings.
        for repair_round in range(rounds):
            async with Session() as session:
                findings = (await session.scalars(select(ReviewFindingRow).where(
                    ReviewFindingRow.run_id == run_id, ReviewFindingRow.status == "open"))).all()
                claims = {c.claim_id: c for c in (await session.scalars(
                    select(ClaimRow).where(ClaimRow.run_id == run_id))).all()}
                evidence = (await session.scalars(select(EvidenceRow).where(EvidenceRow.run_id == run_id))).all()
                by_evidence = {e.evidence_id: e for e in evidence}
                targets = [(f.finding_id, f.claim_id) for f in findings]
            if not targets:
                break
            async with Session() as session:
                for finding_id, claim_id in targets:
                    finding = await session.get(ReviewFindingRow, finding_id)
                    claim = await session.get(ClaimRow, claim_id)
                    if not claim:
                        continue
                    note = "No relevant evidence is linked. Remove, qualify, or attach a source only if actually available."
                    if finding.finding_type == "contradiction":
                        note = "The claim conflicts with another claim. Resolve it only with evidence or qualify both."
                    await bus.send(AgentMessage(run_id=run_id, sender_agent_id=reviewer,
                        recipient_agent_id=claim.owner_agent_id, message_type="finding",
                        related_claim_ids=[claim.claim_id],
                        payload={"claim_id": claim.claim_id, "finding": finding.explanation,
                                 "required_action": finding.required_action, "repair_round": repair_round + 1}))
                    reply = await self._call(adapter, budget, run_id, "targeted_repair", [
                        {"role": "system", "content": "Repair only the specific claim given. Do not alter unrelated work. Return JSON with text, claim_type, evidence_ids, subject, predicate, value, scope, time_context."},
                        {"role": "user", "content": json.dumps({"claim_id": claim.claim_id, "text": claim.text,
                            "claim_type": claim.claim_type, "evidence": [
                                {"evidence_id": e, "excerpt": by_evidence[e].excerpt}
                                for e in claim.evidence_ids if e in by_evidence],
                            "finding": finding.explanation, "required_action": finding.required_action, "guidance": note})}], claim.owner_agent_id)
                    await bus.send(AgentMessage(run_id=run_id, sender_agent_id=claim.owner_agent_id,
                        recipient_agent_id=reviewer, message_type="evidence",
                        related_claim_ids=[claim.claim_id], payload={"claim_id": claim.claim_id,
                                                                     "repair_response": reply}))
                    try:
                        repaired = _json(reply)
                    except (ValueError, TypeError):
                        repaired = {}
                    if repaired.get("text"):
                        claim.text = str(repaired["text"])
                        claim.claim_type = repaired.get("claim_type", claim.claim_type)
                        claim.evidence_ids = [e for e in repaired.get("evidence_ids", claim.evidence_ids) if e in by_evidence]
                        await session.execute(delete(ClaimEvidenceRow).where(
                            ClaimEvidenceRow.run_id == run_id, ClaimEvidenceRow.claim_id == claim.claim_id))
                        for evidence_id in claim.evidence_ids:
                            session.add(ClaimEvidenceRow(run_id=run_id, claim_id=claim.claim_id,
                                                         evidence_id=evidence_id))
                        for key in ("subject", "predicate", "value", "scope", "time_context"):
                            if key in repaired:
                                setattr(claim, key, repaired[key])
                        if claim.claim_type == "fact":
                            claim.verification_status = "supported" if any(
                                self._relevant(claim.text, by_evidence[e].excerpt or "") for e in claim.evidence_ids) else "unsupported"
                        elif claim.claim_type == "calculation":
                            claim.verification_status = "supported" if any(by_evidence[e].source_type == "calculation" for e in claim.evidence_ids) else "qualified"
                        else:
                            claim.verification_status = "qualified"
                        finding.status = ("repaired" if claim.verification_status not in
                                          ("unsupported", "disputed") else "unresolved")
                    else:
                        finding.status = "unresolved"
                await session.commit()
        async with Session() as session:
            reviewer_row = await session.get(AgentRow, reviewer)
            reviewer_row.status = "completed"
            await session.commit()

    async def _synthesize(self, run_id, prompt, outputs, adapter, budget):
        async with Session() as session:
            claims = (await session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id))).all()
            evidence = (await session.scalars(select(EvidenceRow).where(EvidenceRow.run_id == run_id))).all()
            findings = (await session.scalars(select(ReviewFindingRow).where(ReviewFindingRow.run_id == run_id))).all()
            caveats = [f"Unresolved {f.finding_type} finding for claim {f.claim_id}: {f.explanation}" for f in findings
                       if f.status in ("unresolved", "open")]
            for c in claims:
                if c.verification_status in ("unsupported", "disputed"):
                    caveats.append(f"Claim {c.claim_id} is {c.verification_status}; do not present as established fact.")
            approved = []
            for claim in claims:
                if claim.verification_status == "supported":
                    refs = ", ".join(claim.evidence_ids) or "no evidence IDs"
                    approved.append(f"- {claim.text} (claim `{claim.claim_id}`; evidence: {refs})")
                elif claim.verification_status == "qualified" and claim.claim_type in ("inference", "recommendation"):
                    approved.append(f"- Unverified {claim.claim_type}: {claim.text} (claim `{claim.claim_id}`)")
            answer = ("\n".join(approved) if approved else
                      "No worker claims passed the evidence review, so ProofMesh has no substantiated answer to return.")
        return RunResult(run_id=run_id, status="completed", answer=answer,
            caveats=list(dict.fromkeys(caveats)), claim_ids=[c.claim_id for c in claims],
            evidence_index={c.claim_id: c.evidence_ids for c in claims},
            metadata={"mode": "network", "model": adapter.profile.model,
                      "token_usage": budget.used, **self.metrics[run_id],
                      "evidence_count": len(evidence)})


orchestrator = Orchestrator()
