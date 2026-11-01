from uuid import uuid4

import pytest
from sqlalchemy import select

from proofmesh.core.orchestrator import Orchestrator
from proofmesh.schemas.core import WorkOrder
from proofmesh.storage.database import Session, initialize
from proofmesh.storage.models import ClaimRow, RunRow


def test_factual_claim_without_evidence_is_not_supported():
    assert Orchestrator._relevant("The moon has craters", "") is False
    assert Orchestrator._relevant("The moon has craters", "The moon has craters") is True


@pytest.mark.asyncio
async def test_claim_without_evidence_is_stored_as_unsupported():
    await initialize()
    run_id = str(uuid4())
    async with Session() as session:
        session.add(RunRow(run_id=run_id, prompt="p", status="running", stage="worker",
            model_profile={"provider": "mock", "model": "test"}, token_budget=1000,
            token_usage=0, metadata_json={}))
        await session.commit()
    task = WorkOrder(task_id=f"{run_id}:task", run_id=run_id, assigned_agent_id="agent",
                     objective="test")
    await Orchestrator()._store_claims(run_id, task, [{"text": "No source attached",
        "claim_type": "fact"}])
    async with Session() as session:
        claim = await session.scalar(select(ClaimRow).where(ClaimRow.run_id == run_id))
    assert claim.verification_status == "unsupported"
