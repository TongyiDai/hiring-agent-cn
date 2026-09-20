"""End-to-end orchestration for human-reviewable evidence reports."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .ai import GuardedAIReviewer
from .code_hosts import collect_code_evidence
from .documents import DocumentExtractor
from .jobs import parse_job_description
from .matching import build_evidence_matrix, summarize_matrix
from .privacy import PrivacyRedactor
from .schemas import AuditMetadata, EvidenceBlock, ReviewReport


class ReviewEngine:
    def __init__(self, extractor: DocumentExtractor | None = None):
        self.extractor = extractor or DocumentExtractor()
        self.redactor = PrivacyRedactor()

    def review(
        self,
        resume_path: str | Path,
        job_text: str,
        *,
        job_title: str | None = None,
        code_urls: list[str] | None = None,
        confirm_job_profile: bool = False,
        use_ai: bool = False,
        ai_reviewer: GuardedAIReviewer | None = None,
    ) -> ReviewReport:
        extraction = self.extractor.extract(resume_path)
        blind_resume = self.redactor.redact(extraction)
        job = parse_job_description(job_text, title=job_title)
        if not confirm_job_profile:
            raise ValueError(
                "运行前必须由招聘人员确认岗位要求。请设置 confirm_job_profile=True；"
                "若岗位合规检查有命中项，请先人工处理。"
            )
        job = job.model_copy(update={"requires_human_confirmation": False})
        code_evidence = collect_code_evidence(code_urls or [])
        code_blocks = []
        for item in code_evidence:
            if not item.verified or not item.summary:
                continue
            digest = hashlib.sha256(
                f"{item.platform}|{item.url}|{item.summary}".encode()
            ).hexdigest()
            code_blocks.append(
                EvidenceBlock(
                    evidence_id=f"EV-CODE-{digest[:10]}",
                    source_type="code_host",
                    text=item.summary,
                    metadata={"platform": item.platform, "url": item.url},
                )
            )
        if code_blocks:
            blind_resume = blind_resume.model_copy(
                update={
                    "blocks": blind_resume.blocks + code_blocks,
                    "safe_text": blind_resume.safe_text
                    + "\n"
                    + "\n".join(block.text for block in code_blocks),
                }
            )
        matrix = build_evidence_matrix(job, blind_resume)
        warnings = list(extraction.warnings)
        audit = AuditMetadata(
            input_sha256=extraction.source_sha256,
            job_sha256=job.raw_text_sha256,
        )
        if use_ai:
            reviewer = ai_reviewer or GuardedAIReviewer()
            try:
                matrix, ai_warnings = reviewer.refine(matrix)
                warnings.extend(ai_warnings)
                audit.model_provider = reviewer.base_url
                audit.model_name = reviewer.model
            except Exception as exc:
                warnings.append(f"AI 增强失败，已保留确定性审阅结果：{type(exc).__name__}")
        if extraction.security.quarantined_count:
            warnings.append(
                f"安全检测隔离了 {extraction.security.quarantined_count} 段可疑内容；"
                "它们未进入岗位匹配或模型输入，请人工查看安全审计。"
            )
        if job.compliance_findings:
            warnings.append("岗位说明存在需要人工确认的公平招聘风险，不能据此自动筛选。")
        return ReviewReport(
            job=job,
            matrix=matrix,
            summary=summarize_matrix(matrix),
            security=extraction.security,
            redactions=blind_resume.redactions,
            code_evidence=code_evidence,
            warnings=warnings,
            audit=audit,
        )
