import pytest

from proofmesh.core.message_bus import MessageBus
from proofmesh.schemas.core import AgentMessage


@pytest.mark.asyncio
async def test_messages_route_to_recipient_and_persist():
    persisted = []
    async def save(message):
        persisted.append(message.message_id)
    bus = MessageBus(save)
    for recipient in ("b", "c"):
        await bus.send(AgentMessage(run_id="r", sender_agent_id="a", recipient_agent_id=recipient,
            message_type="request", payload={"question": recipient}))
    assert (await bus.receive("r", "b")).payload["question"] == "b"
    assert (await bus.receive("r", "c")).payload["question"] == "c"
    assert len(persisted) == 2
