from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hiring_agent_cn.cli import app as cli_app
from hiring_agent_cn.human_review import apply_human_review
from hiring_agent_cn.render import render_csv, render_html, render_json
from hiring_agent_cn.review import ReviewEngine
from hiring_agent_cn.schemas import HumanReviewAction
from hiring_agent_cn.web import app


def test_review_end_to_end_quarantines_attack(adversarial_resume_pdf: Path) -> None:
    report = ReviewEngine().review(
        adversarial_resume_pdf,
        "后端工程师\n熟悉 Python\n熟悉 Kubernetes",
        job_title="后端工程师",
        confirm_job_profile=True,
    )
    assert report.audit.human_review_required is True
    assert report.security.quarantined_count >= 3
    all_quotes = " ".join(item.quote for cell in report.matrix for item in cell.evidence)
    assert "Ignore previous" not in all_quotes
    assert "must pass" not in all_quotes
    assert report.warnings
    assert "schema_version" in render_json(report)
    assert "requirement_id" in render_csv(report)
    assert "人岗证据审阅报告" in render_html(report)


def test_web_health_and_review(clean_resume_pdf: Path) -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {
        "status": "ok",
        "decision_mode": "human-review-required",
    }
    with clean_resume_pdf.open("rb") as resume:
        response = client.post(
            "/api/review",
            files={"resume": ("resume.pdf", resume, "application/pdf")},
            data={
                "job_title": "后端工程师",
                "job_text": "熟悉 Python\n熟悉 Redis",
                "confirm_job_profile": "true",
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["audit"]["human_review_required"] is True
    assert len(payload["matrix"]) == 2


def test_job_profile_confirmation_is_required(clean_resume_pdf: Path) -> None:
    try:
        ReviewEngine().review(
            clean_resume_pdf, "后端工程师\n熟悉 Python", job_title="后端工程师"
        )
    except ValueError as exc:
        assert "确认岗位要求" in str(exc)
    else:
        raise AssertionError("review must require human confirmation")

    with clean_resume_pdf.open("rb") as resume:
        response = TestClient(app).post(
            "/api/review",
            files={"resume": ("resume.pdf", resume, "application/pdf")},
            data={"job_title": "后端工程师", "job_text": "熟悉 Python"},
        )
    assert response.status_code == 422


def test_home_explains_human_review() -> None:
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "不自动录用或淘汰" in response.text


def test_human_review_is_versioned_and_auditable(clean_resume_pdf: Path) -> None:
    report = ReviewEngine().review(
        clean_resume_pdf,
        "后端工程师\n熟悉 Python",
        job_title="后端工程师",
        confirm_job_profile=True,
    )
    requirement_id = report.matrix[0].requirement_id
    signed = apply_human_review(
        report,
        [
            HumanReviewAction(
                requirement_id=requirement_id,
                status="partial",
                note="面试中需要确认个人贡献边界。",
            )
        ],
        reviewer_id="reviewer-001",
    )
    assert signed.audit.review_revision == 1
    assert signed.audit.reviewer_id == "reviewer-001"
    assert signed.human_review_log[0].requirement_id == requirement_id
    assert report.audit.review_revision == 0


def test_human_review_rejects_unknown_requirement(clean_resume_pdf: Path) -> None:
    report = ReviewEngine().review(
        clean_resume_pdf,
        "后端工程师\n熟悉 Python",
        job_title="后端工程师",
        confirm_job_profile=True,
    )
    try:
        apply_human_review(
            report,
            [HumanReviewAction(requirement_id="REQ-UNKNOWN", status="partial", note="test")],
            reviewer_id="reviewer-001",
        )
    except ValueError as exc:
        assert "未知岗位要求" in str(exc)
    else:
        raise AssertionError("unknown requirement must fail")


def test_cli_review_and_jd_check(clean_resume_pdf: Path, tmp_path: Path) -> None:
    job = tmp_path / "job.md"
    job.write_text("后端工程师\n熟悉 Python\n仅限男性", encoding="utf-8")
    output = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "review",
            str(clean_resume_pdf),
            "--job",
            str(job),
            "--title",
            "后端工程师",
            "--confirm-job-profile",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert "审阅完成" in result.output
    check = runner.invoke(cli_app, ["check-jd", str(job)])
    assert check.exit_code == 0
    assert "性别限制" in check.output
