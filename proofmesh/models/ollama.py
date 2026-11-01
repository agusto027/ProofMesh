import time

import httpx

from proofmesh.models.provider_base import Completion, ModelAdapter


class OllamaAdapter(ModelAdapter):
    async def complete(self, messages):
        started = time.perf_counter()
        base = self.profile.base_url or "http://localhost:11434"
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(base.rstrip("/") + "/api/chat", json={
                "model": self.profile.model, "messages": messages, "stream": False,
                "options": {"temperature": self.profile.temperature,
                            "num_predict": self.profile.max_output_tokens},
            })
            response.raise_for_status()
            body = response.json()
        return Completion(body["message"]["content"], body.get("prompt_eval_count", 0),
                          body.get("eval_count", 0), int((time.perf_counter() - started) * 1000))
