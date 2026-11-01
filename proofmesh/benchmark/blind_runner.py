import random
from uuid import uuid4

from proofmesh.benchmark.baseline import run_baseline
from proofmesh.core.orchestrator import orchestrator
from proofmesh.schemas.core import ModelProfile, RunRequest
from proofmesh.storage.database import Session
from proofmesh.storage.models import BenchmarkPairRow


async def compare_blind(prompt: str, profile: ModelProfile, budget_tokens: int) -> dict:
    # Each mode gets the same per-run budget and exact model profile.
    baseline, network = await run_baseline(prompt, profile, budget_tokens), await orchestrator.run(
        RunRequest(prompt=prompt, model_profile=profile, budget_tokens=budget_tokens))
    network_first = bool(random.getrandbits(1))
    order = "network_first" if network_first else "baseline_first"
    answers = ([network.answer, baseline["answer"]] if network_first
               else [baseline["answer"], network.answer])
    benchmark_id = str(uuid4())
    async with Session() as session:
        session.add(BenchmarkPairRow(benchmark_id=benchmark_id, run_id=network.run_id,
            mapping={"X": "network" if network_first else "baseline",
                     "Y": "baseline" if network_first else "network"},
            randomized_order=order, metadata_json={"prompt": prompt, "model_profile": profile.model_dump(),
                "baseline_run_id": baseline["run_id"], "network_run_id": network.run_id,
                "baseline_metrics": {k: baseline[k] for k in ("token_usage", "model_calls", "latency_ms")},
                "network_metrics": network.metadata}))
        await session.commit()
    return {"benchmark_id": benchmark_id, "responses": {"X": answers[0], "Y": answers[1]}}
