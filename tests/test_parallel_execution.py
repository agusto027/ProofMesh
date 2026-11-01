import asyncio
import time

import pytest

from proofmesh.core.scheduler import execute_ready
from proofmesh.schemas.core import WorkOrder


@pytest.mark.asyncio
async def test_independent_tasks_overlap_and_dependency_waits():
    tasks = [WorkOrder(task_id="a", run_id="r", assigned_agent_id="a", objective="a"),
             WorkOrder(task_id="b", run_id="r", assigned_agent_id="b", objective="b"),
             WorkOrder(task_id="c", run_id="r", assigned_agent_id="c", objective="c", dependencies=["a", "b"])]
    completed, starts = set(), {}
    async def worker(task):
        starts[task.task_id] = time.perf_counter()
        await asyncio.sleep(0.04)
        return task.task_id
    semaphore = asyncio.Semaphore(2)
    first = await execute_ready(tasks, completed, worker, semaphore)
    assert set(first) == {"a", "b"}
    assert abs(starts["a"] - starts["b"]) < 0.03
    completed.update(first)
    second = await execute_ready(tasks, completed, worker, semaphore)
    assert second == ["c"]


@pytest.mark.asyncio
async def test_orchestrator_mock_end_to_end():
    from proofmesh.core.orchestrator import orchestrator
    from proofmesh.schemas.core import ModelProfile, RunRequest
    from proofmesh.storage.database import initialize

    await initialize()
    result = await orchestrator.run(RunRequest(prompt="Summarize the prompt.",
        model_profile=ModelProfile(provider="mock", model="deterministic"), budget_tokens=2000))
    assert result.status == "completed"
    assert result.answer
    second = await orchestrator.run(RunRequest(prompt="Summarize another prompt.",
        model_profile=ModelProfile(provider="mock", model="deterministic"), budget_tokens=2000))
    assert second.status == "completed"
    assert second.run_id != result.run_id
