"""Command line interface for local and batch review."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .documents import DocumentExtractor
from .human_review import apply_human_review
from .jobs import audit_job_description
from .render import write_report
from .review import ReviewEngine
from .schemas import HumanReviewAction, ReviewReport

app = typer.Typer(
    name="hiring-agent-cn",
    help="中文人岗证据审阅：先隔离风险，再引用证据，始终由人决策。",
    no_args_is_help=True,
)


def _load_job(path: Path) -> str:
    if not path.is_file():
        raise typer.BadParameter(f"岗位说明文件不存在：{path}")
    return path.read_text(encoding="utf-8-sig")


@app.command()
def review(
    resume: Annotated[Path, typer.Argument(help="PDF、DOCX、图片或纯文本简历")],
    job: Annotated[Path, typer.Option("--job", "-j", help="UTF-8 岗位说明文件")],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("review-report.html"),
    title: Annotated[str | None, typer.Option("--title")] = None,
    code_url: Annotated[list[str] | None, typer.Option("--code-url")] = None,
    confirm_job_profile: Annotated[
        bool,
        typer.Option("--confirm-job-profile", help="确认已人工核对岗位要求与合规提示"),
    ] = False,
    use_ai: Annotated[
        bool, typer.Option(help="使用配置的模型润色解释；确定性证据上限仍生效")
    ] = False,
) -> None:
    """审阅一份简历并输出 JSON、CSV 或本地 HTML 报告。"""
    report = ReviewEngine().review(
        resume,
        _load_job(job),
        job_title=title,
        code_urls=code_url,
        confirm_job_profile=confirm_job_profile,
        use_ai=use_ai,
    )
    path = write_report(report, output)
    typer.echo(f"审阅完成：{path.resolve()}")
    typer.echo(
        f"有直接证据 {report.summary.supported}｜部分证据 {report.summary.partial}｜"
        f"尚未确认 {report.summary.unverified}｜隔离 {report.security.quarantined_count}"
    )


@app.command("inspect")
def inspect_document(
    resume: Annotated[Path, typer.Argument(help="待检查的候选人材料")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """只运行可见性与提示注入检查，不做岗位匹配。"""
    extraction = DocumentExtractor().extract(resume)
    payload = extraction.model_dump_json(indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        typer.echo(f"检查报告：{output.resolve()}")
    else:
        typer.echo(payload)


@app.command("check-jd")
def check_job(
    job: Annotated[Path, typer.Argument(help="UTF-8 岗位说明文件")],
) -> None:
    """检查岗位文本中的公平招聘风险表述。"""
    findings = [item.model_dump() for item in audit_job_description(_load_job(job))]
    typer.echo(json.dumps({"findings": findings}, ensure_ascii=False, indent=2))


@app.command()
def batch(
    directory: Annotated[Path, typer.Argument(help="简历目录")],
    job: Annotated[Path, typer.Option("--job", "-j")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")] = Path("review-results"),
    title: Annotated[str | None, typer.Option("--title")] = None,
    confirm_job_profile: Annotated[
        bool, typer.Option("--confirm-job-profile", help="确认已人工核对岗位要求")
    ] = False,
) -> None:
    """批量审阅；输出文件仅使用内容哈希，不使用候选人姓名。"""
    engine = ReviewEngine()
    job_text = _load_job(job)
    supported = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
    files = sorted(path for path in directory.iterdir() if path.suffix.lower() in supported)
    if not files:
        raise typer.BadParameter("目录中没有支持的候选人材料。")
    output_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for source in files:
        report = engine.review(
            source,
            job_text,
            job_title=title,
            confirm_job_profile=confirm_job_profile,
        )
        report_name = f"review-{report.audit.input_sha256[:16]}.json"
        destination = write_report(report, output_dir / report_name, "json")
        index.append(
            {
                "report": destination.name,
                "supported": report.summary.supported,
                "partial": report.summary.partial,
                "unverified": report.summary.unverified,
                "quarantined": report.security.quarantined_count,
            }
        )
    (output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(f"完成 {len(files)} 份材料：{output_dir.resolve()}")


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
) -> None:
    """启动仅绑定本机的审阅页面。"""
    import uvicorn

    if host not in {"127.0.0.1", "localhost"}:
        typer.echo("提醒：当前绑定地址会向局域网暴露服务，请确认部署侧已配置访问控制。")
    uvicorn.run("hiring_agent_cn.web:app", host=host, port=port)


@app.command("sign-off")
def sign_off(
    report_path: Annotated[Path, typer.Argument(help="待复核的 JSON 报告")],
    actions_path: Annotated[Path, typer.Option("--actions", "-a", help="人工复核动作 JSON")],
    reviewer: Annotated[
        str, typer.Option("--reviewer", help="审核人标识，可使用内部工号或别名")
    ],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("review-signed.json"),
) -> None:
    """逐条确认或修正证据状态，并保留机器结果和人工审计记录。"""
    report = ReviewReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    raw_actions = json.loads(actions_path.read_text(encoding="utf-8"))
    actions = [HumanReviewAction.model_validate(item) for item in raw_actions]
    signed = apply_human_review(report, actions, reviewer_id=reviewer)
    write_report(signed, output, "json")
    typer.echo(f"人工复核已记录：{output.resolve()}")


if __name__ == "__main__":
    app()
