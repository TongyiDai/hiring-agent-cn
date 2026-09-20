"""Auditable human review without automated hiring decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from .matching import summarize_matrix
from .schemas import HumanReviewAction, ReviewReport


def apply_human_review(
    report: ReviewReport,
    actions: list[HumanReviewAction],
    *,
    reviewer_id: str,
) -> ReviewReport:
    if not reviewer_id.strip():
        raise ValueError("人工复核必须提供审核人标识。")
    by_requirement = {action.requirement_id: action for action in actions}
    known = {cell.requirement_id for cell in report.matrix}
    unknown = set(by_requirement) - known
    if unknown:
        raise ValueError(f"人工复核包含未知岗位要求：{', '.join(sorted(unknown))}")

    matrix = []
    for cell in report.matrix:
        action = by_requirement.get(cell.requirement_id)
        if action:
            matrix.append(
                cell.model_copy(
                    update={
                        "status": action.status,
                        "rationale": f"{cell.rationale} 人工复核：{action.note}",
                    }
                )
            )
        else:
            matrix.append(cell)

    audit = report.audit.model_copy(
        update={
            "review_revision": report.audit.review_revision + 1,
            "reviewer_id": reviewer_id.strip(),
            "reviewed_at": datetime.now(UTC).isoformat(),
        }
    )
    return report.model_copy(
        update={
            "matrix": matrix,
            "summary": summarize_matrix(matrix),
            "human_review_log": report.human_review_log + actions,
            "audit": audit,
        }
    )
