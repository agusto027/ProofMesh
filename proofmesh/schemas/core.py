from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelProfile(Schema):
    provider: Literal["openai_compatible", "ollama", "mock"]
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=2048, ge=1, le=32768)


class TaskStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"


class WorkOrder(Schema):
    task_id: str = Field(default_factory=new_id)
    run_id: str
    assigned_agent_id: str
    objective: str
    deliverable_schema: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    evidence_required: bool = True
    status: TaskStatus = TaskStatus.queued


class TaskPlan(Schema):
    rationale: str
    work_orders: list[WorkOrder]
    required_capabilities: list[str] = Field(default_factory=list)


class AgentMessage(Schema):
    message_id: str = Field(default_factory=new_id)
    run_id: str
    sender_agent_id: str
    recipient_agent_id: str
    message_type: Literal["request", "evidence", "finding", "challenge", "clarification", "status"]
    related_task_ids: list[str] = Field(default_factory=list)
    related_claim_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)


class Claim(Schema):
    claim_id: str = Field(default_factory=new_id)
    run_id: str
    owner_agent_id: str
    text: str
    claim_type: Literal["fact", "calculation", "inference", "recommendation"]
    evidence_ids: list[str] = Field(default_factory=list)
    subject: str | None = None
    predicate: str | None = None
    value: str | None = None
    scope: str | None = None
    time_context: str | None = None
    verification_status: Literal["pending", "supported", "disputed", "unsupported", "qualified"] = "pending"
    review_notes: list[str] = Field(default_factory=list)


class Evidence(Schema):
    evidence_id: str = Field(default_factory=new_id)
    run_id: str
    source_type: Literal["web", "document", "tool_result", "calculation", "user_context"]
    source_uri: str | None = None
    title: str | None = None
    excerpt: str | None = None
    content_digest: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewFinding(Schema):
    finding_id: str = Field(default_factory=new_id)
    run_id: str
    reviewer_agent_id: str
    claim_id: str
    finding_type: Literal["missing_evidence", "weak_support", "contradiction", "stale_source", "unsupported_number", "scope_mismatch"]
    explanation: str
    required_action: str
    status: Literal["open", "repaired", "unresolved", "rejected"] = "open"


class Artifact(Schema):
    artifact_id: str = Field(default_factory=new_id)
    run_id: str
    task_id: str
    agent_id: str
    content: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)


class RunRequest(Schema):
    prompt: str = Field(min_length=1, max_length=20000)
    model_profile: ModelProfile
    max_agents: int = Field(default=5, ge=1, le=20)
    review_rounds: int = Field(default=2, ge=0, le=2)
    budget_tokens: int = Field(default=10000, ge=100, le=1000000)
    context_refs: list[str] = Field(default_factory=list)


class RunResult(Schema):
    run_id: str
    status: str
    answer: str
    caveats: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    evidence_index: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(Schema):
    title: str
    url: HttpUrl
    excerpt: str
