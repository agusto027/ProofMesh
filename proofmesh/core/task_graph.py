from proofmesh.schemas.core import TaskPlan, WorkOrder


def validate_plan(plan: TaskPlan) -> None:
    if not plan.work_orders:
        raise ValueError("Task plan must contain at least one work order.")
    ids = [task.task_id for task in plan.work_orders]
    if len(ids) != len(set(ids)):
        raise ValueError("Task plan contains duplicate task IDs.")
    known = set(ids)
    for task in plan.work_orders:
        unknown = set(task.dependencies) - known
        if unknown:
            raise ValueError(f"Task {task.task_id} has unknown dependencies: {sorted(unknown)}")
        if task.task_id in task.dependencies:
            raise ValueError(f"Task {task.task_id} depends on itself.")
    visited, active = set(), set()

    def visit(task_id):
        if task_id in active:
            raise ValueError("Task plan contains a dependency cycle.")
        if task_id in visited:
            return
        active.add(task_id)
        item = next(t for t in plan.work_orders if t.task_id == task_id)
        for dep in item.dependencies:
            visit(dep)
        active.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)


def normalize_tasks(plan: TaskPlan, run_id: str, max_agents: int) -> list[WorkOrder]:
    validate_plan(plan)
    ids = {task.task_id: f"{run_id}:{task.task_id}" for task in plan.work_orders}
    return [task.model_copy(update={"task_id": ids[task.task_id], "run_id": run_id,
        "assigned_agent_id": f"{run_id}:agent-{i % max_agents + 1}",
        "dependencies": [ids[dependency] for dependency in task.dependencies]})
        for i, task in enumerate(plan.work_orders)]
