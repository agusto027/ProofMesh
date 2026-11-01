import pytest

from proofmesh.core.task_graph import validate_plan
from proofmesh.schemas.core import TaskPlan, WorkOrder


def task(task_id, dependencies=None):
    return WorkOrder(task_id=task_id, run_id="r", assigned_agent_id="a", objective=task_id,
                     dependencies=dependencies or [])


def test_task_graph_accepts_dependency_dag():
    validate_plan(TaskPlan(rationale="ok", work_orders=[task("a"), task("b", ["a"])]))


@pytest.mark.parametrize("orders", [
    [task("a", ["missing"])],
    [task("a", ["b"]), task("b", ["a"])],
])
def test_task_graph_rejects_invalid_graph(orders):
    with pytest.raises(ValueError):
        validate_plan(TaskPlan(rationale="bad", work_orders=orders))
