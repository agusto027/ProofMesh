from proofmesh.models.factory import create_adapter
from proofmesh.schemas.core import ModelProfile


def test_provider_adapters_use_configured_default_endpoints():
    ollama = create_adapter(ModelProfile(provider="ollama", model="local-model"))
    openai = create_adapter(ModelProfile(provider="openai_compatible", model="hosted-model"))
    assert ollama.profile.base_url == "http://localhost:11434"
    assert openai.profile.base_url == "https://api.openai.com/v1"
