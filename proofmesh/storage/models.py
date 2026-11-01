from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from proofmesh.storage.database import Base


def now():
    return datetime.now(UTC)


class RunRow(Base):
    __tablename__ = "runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), index=True)
    stage: Mapped[str] = mapped_column(String(40), default="planning")
    model_profile: Mapped[dict] = mapped_column(JSON)
    token_budget: Mapped[int] = mapped_column(Integer)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AgentRow(Base):
    __tablename__ = "agents"
    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    specialty: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), index=True)


class WorkOrderRow(Base):
    __tablename__ = "work_orders"
    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    assigned_agent_id: Mapped[str] = mapped_column(String(36))
    objective: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), index=True)


class AgentMessageRow(Base):
    __tablename__ = "agent_messages"
    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    sender_agent_id: Mapped[str] = mapped_column(String(36))
    recipient_agent_id: Mapped[str] = mapped_column(String(36))
    message_type: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    artifact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_id: Mapped[str] = mapped_column(String(36))
    content: Mapped[dict] = mapped_column(JSON)


class ClaimRow(Base):
    __tablename__ = "claims"
    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    owner_agent_id: Mapped[str] = mapped_column(String(36))
    text: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(24))
    evidence_ids: Mapped[list] = mapped_column(JSON)
    subject: Mapped[str | None] = mapped_column(String(300))
    predicate: Mapped[str | None] = mapped_column(String(300))
    value: Mapped[str | None] = mapped_column(String(500))
    scope: Mapped[str | None] = mapped_column(String(300))
    time_context: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(String(24), index=True)
    review_notes: Mapped[list] = mapped_column(JSON)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    source_type: Mapped[str] = mapped_column(String(24))
    source_uri: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    content_digest: Mapped[str | None] = mapped_column(String(128))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source_metadata: Mapped[dict] = mapped_column(JSON)


class ClaimEvidenceRow(Base):
    __tablename__ = "claim_evidence"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), primary_key=True, index=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), primary_key=True, index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.evidence_id"), primary_key=True, index=True)


class ReviewFindingRow(Base):
    __tablename__ = "review_findings"
    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    reviewer_agent_id: Mapped[str] = mapped_column(String(36))
    claim_id: Mapped[str] = mapped_column(String(36), index=True)
    finding_type: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text)
    required_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), index=True)


class BenchmarkPairRow(Base):
    __tablename__ = "benchmark_pairs"
    benchmark_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    mapping: Mapped[dict] = mapped_column(JSON)
    randomized_order: Mapped[str] = mapped_column(String(24))
    metadata_json: Mapped[dict] = mapped_column(JSON)


class UsageEventRow(Base):
    __tablename__ = "usage_events"
    usage_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36))
    purpose: Mapped[str] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(nullable=True)


Index("ix_claim_run_evidence", ClaimRow.run_id, ClaimRow.verification_status)
Index("ix_evidence_run", EvidenceRow.run_id, EvidenceRow.evidence_id)
