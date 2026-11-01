import asyncio


async def execute_ready(tasks, completed: set[str], worker, semaphore: asyncio.Semaphore):
    """Execute one dependency-ready layer concurrently and return worker results."""
    ready = [task for task in tasks if task.task_id not in completed and
             set(task.dependencies) <= completed]
    if not ready:
        if len(completed) != len(tasks):
            raise ValueError("Task graph cannot make progress.")
        return []

    async def bounded(task):
        async with semaphore:
            return await worker(task)

    return await asyncio.gather(*(bounded(task) for task in ready))
