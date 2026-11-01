import pytest
from sqlalchemy import select

from proofmesh.benchmark.blind_runner import compare_blind
from proofmesh.schemas.core import ModelProfile
from proofmesh.storage.database import Session, initialize
from proofmesh.storage.models import BenchmarkPairRow


@pytest.mark.asyncio
async def test_blind_outputs_do_not_include_mapping(monkeypatch):
    await initialize()
    monkeypatch.setattr("proofmesh.benchmark.blind_runner.random.getrandbits", lambda _: 1)
    result = await compare_blind("Summarize this prompt", ModelProfile(provider="mock", model="same"), 2000)
    assert set(result["responses"]) == {"X", "Y"}
    assert "mapping" not in result
    async with Session() as session:
        record = await session.scalar(select(BenchmarkPairRow).where(
            BenchmarkPairRow.benchmark_id == result["benchmark_id"]))
        assert record.mapping == {"X": "network", "Y": "baseline"}
