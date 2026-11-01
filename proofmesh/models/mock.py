import json

from proofmesh.models.provider_base import Completion, ModelAdapter


class MockAdapter(ModelAdapter):
    """Deterministic, keyless adapter for local smoke tests and CI."""
    async def complete(self, messages):
        system = messages[0]["content"] if messages else ""
        last = messages[-1]["content"] if messages else ""
        if "lead planner" in system:
            text = json.dumps({"rationale": "Single work order keeps the request atomic.", "work_orders": [{
                "task_id": "task-1", "run_id": "", "assigned_agent_id": "", "objective": last[:200],
                "deliverable_schema": {"summary": "string"}, "dependencies": [],
                "acceptance_criteria": ["Answer the assigned objective"],
                "allowed_capabilities": ["calculate", "web_search"], "evidence_required": True,
                "status": "queued"}], "required_capabilities": []})
        elif "Synthesize" in system:
            text = json.dumps({"answer": "Mock synthesis completed. No factual claims were asserted.", "caveats": []})
        elif "baseline" in system:
            text = json.dumps({"answer": "Mock baseline completed. No factual claims were asserted.", "claims": [], "evidence_requests": []})
        else:
            text = json.dumps({"summary": "This response was produced by the deterministic mock adapter.",
                               "claims": [], "evidence": []})
        return Completion(text, max(1, len(last) // 4), max(1, len(text) // 4), 1)
