from proofmesh.app.config import get_settings
from proofmesh.models.mock import MockAdapter
from proofmesh.models.ollama import OllamaAdapter
from proofmesh.models.openai_compatible import OpenAICompatibleAdapter
from proofmesh.schemas.core import ModelProfile


def create_adapter(profile: ModelProfile):
    if profile.provider == "ollama" and not profile.base_url:
        profile = profile.model_copy(update={"base_url": get_settings().ollama_base_url})
    if profile.provider == "openai_compatible" and not profile.base_url:
        profile = profile.model_copy(update={"base_url": get_settings().openai_base_url})
    return {"mock": MockAdapter, "ollama": OllamaAdapter,
            "openai_compatible": OpenAICompatibleAdapter}[profile.provider](profile)
