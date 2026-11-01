from uuid import uuid4

import pytest

from proofmesh.app.mcp_server import proofmesh_get_evidence
from proofmesh.storage.database import Session, initialize
from proofmesh.storage.models import ClaimRow, RunRow


@pytest.mark.asyncio
async def test_evidence_lookup_is_run_scoped():
    run_id, claim_id = str(uuid4()), str(uuid4())
    await initialize()
    async with Session() as session:
        session.add(RunRow(run_id=run_id, prompt="p", status="completed", stage="done",
            model_profile={"provider": "mock", "model": "test"}, token_budget=100, token_usage=0,
            metadata_json={}))
        session.add(ClaimRow(claim_id=claim_id, run_id=run_id,
            owner_agent_id="a", text="x", claim_type="fact", evidence_ids=[], verification_status="unsupported",
            review_notes=[]))
        await session.commit()
    result = await proofmesh_get_evidence("other-run", claim_id)
    assert result == {"error": "claim_not_found"}
