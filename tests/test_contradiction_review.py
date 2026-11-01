from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from proofmesh.core.budget import TokenBudget
from proofmesh.core.message_bus import MessageBus
from proofmesh.core.orchestrator import orchestrator
from proofmesh.storage.database import Session, initialize
from proofmesh.storage.models import AgentRow, ClaimRow, ReviewFindingRow, RunRow


@pytest.mark.asyncio
async def test_conflicting_claims_are_flagged_and_surface_in_final_caveats():
    await initialize()
    run_id = str(uuid4())
    async with Session() as session:
        session.add(RunRow(run_id=run_id, prompt="Check values", status="running", stage="reviewing",
            model_profile={"provider": "mock", "model": "test"}, token_budget=1000,
            token_usage=0, metadata_json={}))
        session.add(AgentRow(agent_id=f"{run_id}:reviewer-1", run_id=run_id, role="reviewer",
            specialty="review", status="idle"))
        for value in ("12", "14"):
            session.add(ClaimRow(claim_id=str(uuid4()), run_id=run_id, owner_agent_id=f"{run_id}:agent",
                text=f"The reported value is {value}", claim_type="inference", evidence_ids=[],
                subject="reported value", predicate="equals", value=value, scope="same report",
                time_context="same period", verification_status="qualified", review_notes=[]))
        await session.commit()
    await orchestrator._review(run_id, 0, {}, None, TokenBudget(1000), MessageBus())
    async with Session() as session:
        findings = (await session.scalars(select(ReviewFindingRow).where(
            ReviewFindingRow.run_id == run_id))).all()
        claims = (await session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id))).all()
    assert sum(f.finding_type == "contradiction" for f in findings) == 2
    assert all(c.verification_status == "disputed" for c in claims)
    adapter = SimpleNamespace(profile=SimpleNamespace(model="test"))
    result = await orchestrator._synthesize(run_id, "Check values", {}, adapter, TokenBudget(1000))
    assert any("contradict" in caveat.lower() for caveat in result.caveats)
