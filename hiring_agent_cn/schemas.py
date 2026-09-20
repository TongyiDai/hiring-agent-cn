"""Shared, versioned data contracts for the safe review pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "low", "medium", "high", "critical"]
EvidenceStatus = Literal["supported", "partial", "unverified", "conflict"]
RequirementPriority = Literal["must", "preferred", "responsibility"]


class EvidenceBlock(BaseModel):
    evidence_id: str
    source_type: Literal["pdf", "docx", "image_ocr", "text", "code_host"]
    page_number: int | None = None
    text: str
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecurityFinding(BaseModel):
    finding_id: str
    kind: str
    severity: Severity
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    text_sha256: str
    text_preview: str
    reasons: list[str]
    action: Literal["quarantined", "warned", "allowed"] = "quarantined"


class SecurityReport(BaseModel):
    detector_version: str = "1.0"
    findings: list[SecurityFinding] = Field(default_factory=list)
    probe_warnings: list[str] = Field(default_factory=list)

    @property
    def quarantined_count(self) -> int:
        return sum(item.action == "quarantined" for item in self.findings)

    @property
    def highest_severity(self) -> Severity:
        order = ["info", "low", "medium", "high", "critical"]
        if not self.findings:
            return "info"
        return max((item.severity for item in self.findings), key=order.index)


class DocumentExtraction(BaseModel):
    schema_version: str = "1.0"
    source_name: str
    source_sha256: str
    media_type: str
    blocks: list[EvidenceBlock]
    safe_text: str
    security: SecurityReport
    warnings: list[str] = Field(default_factory=list)


class RedactionRecord(BaseModel):
    kind: str
    placeholder: str
    value_sha256: str
    evidence_id: str


class BlindResume(BaseModel):
    schema_version: str = "1.0"
    source_sha256: str
    blocks: list[EvidenceBlock]
    safe_text: str
    redactions: list[RedactionRecord] = Field(default_factory=list)


class ComplianceFinding(BaseModel):
    rule_id: str
    category: str
    severity: Severity
    matched_text: str
    explanation: str
    suggestion: str


class JobRequirement(BaseModel):
    requirement_id: str
    text: str
    priority: RequirementPriority
    category: str
    keywords: list[str] = Field(default_factory=list)


class JobProfile(BaseModel):
    schema_version: str = "1.0"
    title: str
    raw_text_sha256: str
    requirements: list[JobRequirement]
    compliance_findings: list[ComplianceFinding] = Field(default_factory=list)
    requires_human_confirmation: bool = True


class EvidenceReference(BaseModel):
    evidence_id: str
    quote: str
    page_number: int | None = None
    relevance: float = Field(ge=0, le=1)


class MatchCell(BaseModel):
    requirement_id: str
    requirement: str
    priority: RequirementPriority
    status: EvidenceStatus
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    rationale: str
    interview_question: str


class CodeEvidence(BaseModel):
    platform: str
    url: str
    verified: bool
    summary: str
    metrics: dict[str, int | float | str | None] = Field(default_factory=dict)
    warning: str | None = None


class ReviewSummary(BaseModel):
    supported: int = 0
    partial: int = 0
    unverified: int = 0
    conflict: int = 0
    note: str = "本结果用于安排人工阅读与面试核验，不构成录用或淘汰决定。"


class AuditMetadata(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    engine_version: str = "1.0.0"
    policy_version: str = "cn-evidence-review-1.0"
    model_provider: str = "deterministic"
    model_name: str = "none"
    human_review_required: bool = True
    input_sha256: str = ""
    job_sha256: str = ""
    review_revision: int = 0
    reviewer_id: str | None = None
    reviewed_at: str | None = None


class HumanReviewAction(BaseModel):
    requirement_id: str
    status: EvidenceStatus
    note: str = Field(min_length=1, max_length=1000)


class ReviewReport(BaseModel):
    schema_version: str = "1.0"
    job: JobProfile
    matrix: list[MatchCell]
    summary: ReviewSummary
    security: SecurityReport
    redactions: list[RedactionRecord]
    code_evidence: list[CodeEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_log: list[HumanReviewAction] = Field(default_factory=list)
    audit: AuditMetadata = Field(default_factory=AuditMetadata)
