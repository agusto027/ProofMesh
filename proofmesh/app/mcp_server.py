from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from proofmesh.app.config import get_settings
from proofmesh.benchmark.blind_runner import compare_blind
from proofmesh.core.orchestrator import orchestrator
from proofmesh.evidence.registry import list_capabilities
from proofmesh.schemas.core import ModelProfile, RunRequest
from proofmesh.storage.database import Session, initialize
from proofmesh.storage.models import (
    AgentRow,
    BenchmarkPairRow,
    ClaimRow,
    EvidenceRow,
    ReviewFindingRow,
    RunRow,
    WorkOrderRow,
)

mcp = FastMCP("ProofMesh", instructions="Evidence-first dynamic task orchestration. Use proofmesh_run_task to execute a request; inspect its ledger with the run, result, and evidence tools.", host=get_settings().host, port=get_settings().port)


@mcp.tool(name="proofmesh_run_task", description="Plan and execute a prompt with dynamic specialist workers, evidence review, and a shared token budget. Returns run_id and status.")
async def proofmesh_run_task(prompt: str, model_profile: dict, max_agents: int = 5,
                             review_rounds: int = 2, budget_tokens: int = 10000,
                             context_refs: list[str] | None = None) -> dict:
    await initialize()
    request = RunRequest(prompt=prompt, model_profile=ModelProfile.model_validate(model_profile),
        max_agents=max_agents, review_rounds=review_rounds, budget_tokens=budget_tokens,
        context_refs=context_refs or [])
    result = await orchestrator.run(request)
    return {"run_id": result.run_id, "status": result.status}


@mcp.tool(name="proofmesh_get_run", description="Retrieve run status, current stage, active agents, completed tasks, token usage, and timestamps for one run.")
async def proofmesh_get_run(run_id: str) -> dict:
    await initialize()
    async with Session() as session:
        run = await session.get(RunRow, run_id)
        if not run:
            return {"error": "run_not_found"}
        agents = (await session.scalars(select(AgentRow).where(AgentRow.run_id == run_id))).all()
        tasks = (await session.scalars(select(WorkOrderRow).where(WorkOrderRow.run_id == run_id))).all()
        return {"run_id": run_id, "status": run.status, "current_stage": run.stage,
            "active_agents": [a.agent_id for a in agents if a.status == "running"],
            "completed_tasks": [t.task_id for t in tasks if t.status == "completed"],
            "token_usage": run.token_usage, "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat()}


@mcp.tool(name="proofmesh_get_result", description="Retrieve the final answer, caveats, claim IDs, evidence index, and benchmark metadata for a run.")
async def proofmesh_get_result(run_id: str) -> dict:
    await initialize()
    async with Session() as session:
        run = await session.get(RunRow, run_id)
        if not run:
            return {"error": "run_not_found"}
        claims = (await session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id))).all()
        findings = (await session.scalars(select(ReviewFindingRow).where(ReviewFindingRow.run_id == run_id))).all()
        benchmark = await session.scalar(select(BenchmarkPairRow).where(BenchmarkPairRow.run_id == run_id))
        metadata = dict(run.metadata_json or {})
        if benchmark:
            metadata["benchmark"] = {"benchmark_id": benchmark.benchmark_id,
                "randomized_order": benchmark.randomized_order, **benchmark.metadata_json}
        return {"run_id": run_id, "status": run.status, "answer": run.answer or "",
            "caveats": [f.explanation for f in findings if f.status in ("open", "unresolved")],
            "claim_ids": [c.claim_id for c in claims],
            "evidence_index": {c.claim_id: c.evidence_ids for c in claims},
            "metadata": metadata}


@mcp.tool(name="proofmesh_get_evidence", description="Retrieve evidence linked to a claim plus review history. Run scoping prevents cross-run disclosure.")
async def proofmesh_get_evidence(run_id: str, claim_id: str) -> dict:
    await initialize()
    async with Session() as session:
        claim = await session.get(ClaimRow, claim_id)
        if not claim or claim.run_id != run_id:
            return {"error": "claim_not_found"}
        evidence = (await session.scalars(select(EvidenceRow).where(EvidenceRow.run_id == run_id,
            EvidenceRow.evidence_id.in_(claim.evidence_ids or [])))).all()
        findings = (await session.scalars(select(ReviewFindingRow).where(
            ReviewFindingRow.run_id == run_id, ReviewFindingRow.claim_id == claim_id))).all()
        return {"run_id": run_id, "claim_id": claim_id, "verification_status": claim.verification_status,
            "evidence": [{"evidence_id": e.evidence_id, "source_type": e.source_type,
                "source_uri": e.source_uri, "title": e.title, "excerpt": e.excerpt,
                "retrieved_at": e.retrieved_at.isoformat(), "source_metadata": e.source_metadata}
                for e in evidence],
            "review_history": [{"finding_id": f.finding_id, "finding_type": f.finding_type,
                "explanation": f.explanation, "required_action": f.required_action, "status": f.status}
                for f in findings]}


@mcp.tool(name="proofmesh_compare_blind", description="Run a blind baseline-versus-network comparison with identical model profile and prompt. Returns anonymized X/Y responses; identity mapping remains private in the benchmark ledger.")
async def proofmesh_compare_blind(prompt: str, model_profile: dict, budget_tokens: int = 10000) -> dict:
    await initialize()
    return await compare_blind(prompt, ModelProfile.model_validate(model_profile), budget_tokens)


@mcp.tool(name="proofmesh_list_capabilities", description="List configured model adapters and evidence capabilities without returning secrets.")
async def proofmesh_list_capabilities() -> dict:
    return list_capabilities(get_settings())
