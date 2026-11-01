import asyncio
from collections import defaultdict

from proofmesh.schemas.core import AgentMessage


class MessageBus:
    """In-process recipient-routed bus; persistence callback records every delivery."""
    def __init__(self, persist=None):
        self.queues = defaultdict(asyncio.Queue)
        self.persist = persist

    async def send(self, message: AgentMessage):
        if self.persist:
            await self.persist(message)
        await self.queues[(message.run_id, message.recipient_agent_id)].put(message)

    async def receive(self, run_id: str, recipient_agent_id: str, timeout: float = 0.1):
        return await asyncio.wait_for(self.queues[(run_id, recipient_agent_id)].get(), timeout)
