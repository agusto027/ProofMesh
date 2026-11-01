from abc import ABC, abstractmethod
from dataclasses import dataclass

from proofmesh.schemas.core import ModelProfile


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ModelAdapter(ABC):
    def __init__(self, profile: ModelProfile):
        self.profile = profile

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> Completion: ...
