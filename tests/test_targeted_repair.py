import json

import pytest
from sqlalchemy import select

from proofmesh.core.orchestrator import orchestrator
from proofmesh.schemas.core import ModelProfile, RunRequest
from proofmesh.storage.database import Session, initialize
from proofmesh.storage.models import ClaimRow


class ScriptedAdapter:
    def __init__(self, profile):
        self.profile = profile

    async def complete(self, messages):
        system = messages[0]["content"]
        user = messages[-1]["content"]
        if "lead planner" in system:
            result = {"rationale": "Two independent tasks.", "work_orders": [
                {"task_id": "repair", "objective": "Create a claim to review", "dependencies": [],
                 "deliverable_schema": {}, "acceptance_criteria": [], "allowed_capabilities": []},
                {"task_id": "preserve", "objective": "Create an unrelated claim", "dependencies": [],
                 "deliverable_schema": {}, "acceptance_criteria": [], "allowed_capabilities": []}]}
        elif "task-specific" in system:
            objective = json.loads(user)["objective"]
            if "unrelated" in objective:
                result = {"summary": "Unrelated", "claims": [{"text": "Unaffected recommendation",
                    "claim_type": "recommendation"}], "evidence_requests": []}
            else:
                result = {"summary": "To be repaired", "claims": [{"text": "Original unsupported fact",
                    "claim_type": "fact"}], "evidence_requests": []}
        elif "Repair only the specific claim" in system:
            result = {"text": "Qualified after review", "claim_type": "inference", "evidence_ids": []}
        else:
            result = {"verdict": "qualified", "reason": "No support."}
        encoded = json.dumps(result)
        from proofmesh.models.provider_base import Completion
        return Completion(encoded, 10, 10, 1)


@pytest.mark.asyncio
async def test_repair_changes_only_the_claim_with_a_finding(monkeypatch):
    await initialize()
    monkeypatch.setattr("proofmesh.core.orchestrator.create_adapter", ScriptedAdapter)
    result = await orchestrator.run(RunRequest(prompt="Review this task", model_profile=ModelProfile(
        provider="mock", model="scripted"), review_rounds=1, budget_tokens=5000))
    async with Session() as session:
        rows = (await session.scalars(select(ClaimRow).where(ClaimRow.run_id == result.run_id))).all()
    by_text = {row.text: row for row in rows}
    assert by_text["Qualified after review"].verification_status == "qualified"
    assert by_text["Unaffected recommendation"].text == "Unaffected recommendation"
    assert len(rows) == 2
