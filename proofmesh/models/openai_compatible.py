import os
import time

import httpx

from proofmesh.models.provider_base import Completion, ModelAdapter


class OpenAICompatibleAdapter(ModelAdapter):
    async def complete(self, messages):
        started = time.perf_counter()
        base = self.profile.base_url or os.getenv("PROOFMESH_OPENAI_BASE_URL", "https://api.openai.com/v1")
        key = os.getenv("PROOFMESH_OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                base.rstrip("/") + "/chat/completions", headers=headers,
                json={"model": self.profile.model, "messages": messages,
                      "temperature": self.profile.temperature,
                      "max_tokens": self.profile.max_output_tokens},
            )
            response.raise_for_status()
            body = response.json()
        usage = body.get("usage", {})
        return Completion(body["choices"][0]["message"]["content"],
                          usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                          int((time.perf_counter() - started) * 1000))
