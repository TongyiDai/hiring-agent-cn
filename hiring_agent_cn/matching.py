"""Evidence-first matching with deterministic ceilings."""

from __future__ import annotations

import re
from collections import Counter

from .jobs import extract_keywords
from .schemas import BlindResume, EvidenceReference, JobProfile, MatchCell, ReviewSummary
from .security import normalize_untrusted_text

STATUS_RANK = {"unverified": 0, "partial": 1, "supported": 2, "conflict": 0}
ABSENCE_RE = re.compile(
    r"(?:未说明|未提及|没有提及|暂无|无相关|缺少|not mentioned|no evidence|does not mention)",
    re.IGNORECASE,
)
NEGATIVE_RE = re.compile(
    r"(?:不具备|没有|从未|不会|不熟悉|not experienced|do not have|does not have)",
    re.IGNORECASE,
)


def _tokens(text: str) -> set[str]:
    normalized = normalize_untrusted_text(text).lower()
    terms = {item.lower() for item in extract_keywords(normalized)}
    terms.update(re.findall(r"[a-z][a-z0-9.+#-]{1,24}", normalized))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", normalized))
    terms.update(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return {term for term in terms if len(term) >= 2}


def _score(requirement: str, keywords: list[str], evidence: str) -> float:
    evidence_lower = normalize_untrusted_text(evidence).lower()
    if ABSENCE_RE.search(evidence_lower) or NEGATIVE_RE.search(evidence_lower):
        return 0.0
    explicit = [word.lower() for word in keywords if len(word) >= 2]
    if explicit:
        matches = sum(word in evidence_lower for word in explicit)
        explicit_score = matches / len(explicit)
    else:
        explicit_score = 0.0
    req_tokens = _tokens(requirement)
    evidence_tokens = _tokens(evidence)
    overlap = len(req_tokens & evidence_tokens) / max(1, len(req_tokens))
    return min(1.0, 0.65 * explicit_score + 0.35 * overlap)


def build_evidence_matrix(job: JobProfile, resume: BlindResume) -> list[MatchCell]:
    matrix: list[MatchCell] = []
    for requirement in job.requirements:
        ranked = sorted(
            (
                (_score(requirement.text, requirement.keywords, block.text), block)
                for block in resume.blocks
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        selected = [(score, block) for score, block in ranked[:3] if score >= 0.15]
        best_score = selected[0][0] if selected else 0.0
        negative_mentions = [
            block
            for block in resume.blocks
            if NEGATIVE_RE.search(block.text)
            and _tokens(requirement.text) & _tokens(block.text)
        ]
        if best_score >= 0.55:
            status = "supported"
            rationale = "简历中存在与该要求直接对应的可追溯证据。"
        elif best_score >= 0.25:
            status = "partial"
            rationale = "简历中存在相关表述，但范围、深度或结果证据不足。"
        elif negative_mentions:
            status = "conflict"
            rationale = "当前材料明确表示缺少或不具备相关经历，需要人工核对表述是否准确。"
        else:
            status = "unverified"
            rationale = "当前材料未提供足够证据；这不等于候选人不具备该能力。"
        evidence = [
            EvidenceReference(
                evidence_id=block.evidence_id,
                quote=block.text[:280],
                page_number=block.page_number,
                relevance=round(score, 3),
            )
            for score, block in selected
        ]
        if status == "supported":
            question = (
                f"请结合一个具体场景说明你如何运用“{requirement.text[:36]}”，以及可量化结果。"
            )
        elif status == "partial":
            question = (
                f"简历对“{requirement.text[:36]}”提及有限，请补充你的职责边界、难点与结果。"
            )
        elif status == "conflict":
            question = f"材料对“{requirement.text[:36]}”存在否定或冲突表述，请确认实际情况。"
        else:
            question = f"现有材料未确认“{requirement.text[:36]}”，请说明是否具备并提供实例。"
        matrix.append(
            MatchCell(
                requirement_id=requirement.requirement_id,
                requirement=requirement.text,
                priority=requirement.priority,
                status=status,  # type: ignore[arg-type]
                confidence=round(best_score, 3),
                evidence=evidence,
                rationale=rationale,
                interview_question=question,
            )
        )
    return matrix


def summarize_matrix(matrix: list[MatchCell]) -> ReviewSummary:
    counts = Counter(cell.status for cell in matrix)
    return ReviewSummary(
        supported=counts["supported"],
        partial=counts["partial"],
        unverified=counts["unverified"],
        conflict=counts["conflict"],
    )
