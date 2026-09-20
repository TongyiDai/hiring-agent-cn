from pathlib import Path

from hiring_agent_cn.documents import DocumentExtractor
from hiring_agent_cn.jobs import audit_job_description, parse_job_description
from hiring_agent_cn.matching import build_evidence_matrix, summarize_matrix
from hiring_agent_cn.privacy import PrivacyRedactor


def test_redacts_identifiers_before_matching(tmp_path: Path) -> None:
    source = tmp_path / "resume.txt"
    source.write_text(
        "姓名：张三\n性别：男\n手机：13800138000\n邮箱：candidate@example.com\n"
        "后端工程师，使用 Python 和 FastAPI 开发订单服务。",
        encoding="utf-8",
    )
    extraction = DocumentExtractor().extract(source)
    blind = PrivacyRedactor().redact(extraction)
    assert "张三" not in blind.safe_text
    assert "13800138000" not in blind.safe_text
    assert "candidate@example.com" not in blind.safe_text
    assert "Python" in blind.safe_text
    assert {record.kind for record in blind.redactions} >= {"name", "phone", "email", "gender"}


def test_flags_job_description_risks() -> None:
    findings = audit_job_description(
        "仅限男性，年龄 35 岁以下，985 院校优先，已婚已育优先，本地户籍。"
    )
    categories = {item.category for item in findings}
    assert {"性别限制", "年龄门槛", "院校标签", "婚育条件", "户籍地域限制"}.issubset(categories)


def test_builds_evidence_matrix_without_treating_missing_as_failure(tmp_path: Path) -> None:
    source = tmp_path / "resume.txt"
    source.write_text(
        "后端工程师\n使用 Python、FastAPI 和 PostgreSQL 构建支付系统。\n负责接口设计与上线。",
        encoding="utf-8",
    )
    blind = PrivacyRedactor().redact(DocumentExtractor().extract(source))
    job = parse_job_description(
        "后端工程师\n熟悉 Python 和 FastAPI\n具备 Kubernetes 生产经验\n负责后端服务设计与交付",
        title="后端工程师",
    )
    matrix = build_evidence_matrix(job, blind)
    assert len(matrix) == 3
    assert matrix[0].status in {"supported", "partial"}
    kubernetes = next(cell for cell in matrix if "Kubernetes" in cell.requirement)
    assert kubernetes.status == "unverified"
    assert "不等于候选人不具备" in kubernetes.rationale
    summary = summarize_matrix(matrix)
    assert summary.unverified >= 1


def test_markdown_heading_and_absence_statement_are_not_evidence(tmp_path: Path) -> None:
    source = tmp_path / "resume.txt"
    source.write_text(
        "使用 Docker 编排开发环境。\n简历未说明 Kubernetes 生产经验。",
        encoding="utf-8",
    )
    blind = PrivacyRedactor().redact(DocumentExtractor().extract(source))
    job = parse_job_description(
        "# 后端工程师\n- 有 Docker 或 Kubernetes 实践者优先", title="后端工程师"
    )
    assert len(job.requirements) == 1
    matrix = build_evidence_matrix(job, blind)
    quotes = [item.quote for item in matrix[0].evidence]
    assert all("未说明 Kubernetes" not in quote for quote in quotes)
    assert any("Docker" in quote for quote in quotes)
