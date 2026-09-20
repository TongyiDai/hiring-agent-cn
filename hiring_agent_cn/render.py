"""Human-readable exports that keep evidence and caveats visible."""

from __future__ import annotations

import csv
import html
from io import StringIO
from pathlib import Path

from .schemas import ReviewReport

STATUS_LABELS = {
    "supported": "有直接证据",
    "partial": "部分证据",
    "unverified": "尚未确认",
    "conflict": "信息冲突",
}
PRIORITY_LABELS = {
    "must": "必备",
    "preferred": "优先",
    "responsibility": "职责",
}


def render_json(report: ReviewReport) -> str:
    return report.model_dump_json(indent=2)


def render_csv(report: ReviewReport) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "requirement_id",
            "requirement",
            "priority",
            "status",
            "confidence",
            "evidence_ids",
            "evidence_quotes",
            "rationale",
            "interview_question",
        ],
    )
    writer.writeheader()
    for cell in report.matrix:
        writer.writerow(
            {
                "requirement_id": cell.requirement_id,
                "requirement": cell.requirement,
                "priority": PRIORITY_LABELS[cell.priority],
                "status": STATUS_LABELS[cell.status],
                "confidence": cell.confidence,
                "evidence_ids": " | ".join(item.evidence_id for item in cell.evidence),
                "evidence_quotes": " | ".join(item.quote for item in cell.evidence),
                "rationale": cell.rationale,
                "interview_question": cell.interview_question,
            }
        )
    return output.getvalue()


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_html(report: ReviewReport) -> str:
    compliance = (
        "".join(
            f"<li><strong>{_escape(item.category)}</strong>：{_escape(item.matched_text)}"
            f"<br><span>{_escape(item.explanation)} {_escape(item.suggestion)}</span></li>"
            for item in report.job.compliance_findings
        )
        or "<li>未命中内置的高风险招聘表述规则；仍需人工复核。</li>"
    )
    rows = []
    for cell in report.matrix:
        evidence = (
            "<br>".join(
                f"<code>{_escape(item.evidence_id)}</code> {_escape(item.quote)}"
                + (f"（第 {item.page_number} 页）" if item.page_number else "")
                for item in cell.evidence
            )
            or "暂无可引用证据"
        )
        rows.append(
            "<tr>"
            f"<td>{_escape(cell.requirement)}</td>"
            f"<td><span class='tag {_escape(cell.status)}'>{_escape(STATUS_LABELS[cell.status])}</span>"
            f"<br><small>置信度 {cell.confidence:.2f}</small></td>"
            f"<td>{evidence}</td>"
            f"<td>{_escape(cell.interview_question)}</td>"
            "</tr>"
        )
    findings = (
        "".join(
            f"<li><code>{_escape(item.finding_id)}</code> <strong>{_escape(item.kind)}</strong>"
            f"，第 {_escape(item.page_number or '-')} 页，原因：{_escape(', '.join(item.reasons))}</li>"
            for item in report.security.findings
        )
        or "<li>未发现内置规则可识别的隐藏文本或提示注入。</li>"
    )
    warnings = "".join(f"<li>{_escape(item)}</li>" for item in report.warnings) or "<li>无</li>"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{_escape(report.job.title)}｜人岗证据审阅</title>
<style>
:root{{--blue:#2f6bff;--ink:#111827;--muted:#667085;--line:#e5e7eb;--bg:#f6f8fb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:48px 24px 80px}}h1{{font-size:34px;margin:0 0 8px}}h2{{margin-top:38px}}.lead{{color:var(--muted);margin:0 0 28px}}
.notice{{border-left:4px solid var(--blue);background:white;padding:16px 20px;border-radius:8px;margin:24px 0}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.metric{{background:white;border:1px solid var(--line);border-radius:12px;padding:18px}}.metric b{{display:block;font-size:28px}}
.table-wrap{{overflow-x:auto;background:white;border:1px solid var(--line);border-radius:12px}}table{{width:100%;border-collapse:collapse;min-width:920px}}th,td{{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid var(--line)}}th{{background:#f9fafb}}
.tag{{display:inline-block;padding:2px 8px;border-radius:999px;background:#eef2ff}}.supported{{color:#175cd3}}.partial{{color:#b54708}}.unverified{{color:#475467}}.conflict{{color:#b42318}}
code{{font-size:12px;color:#344054}}ul{{padding-left:20px}}small,.muted{{color:var(--muted)}}@media(max-width:720px){{.summary{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<h1>{_escape(report.job.title)}</h1><p class="lead">人岗证据审阅报告 · 不是自动录用或淘汰决定</p>
<div class="notice">{_escape(report.summary.note)}</div>
<section class="summary"><div class="metric"><b>{report.summary.supported}</b>有直接证据</div><div class="metric"><b>{report.summary.partial}</b>部分证据</div><div class="metric"><b>{report.summary.unverified}</b>尚未确认</div><div class="metric"><b>{report.security.quarantined_count}</b>已隔离内容</div></section>
<h2>人岗证据矩阵</h2><div class="table-wrap"><table><thead><tr><th>岗位要求</th><th>状态</th><th>简历证据</th><th>面试核验问题</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<h2>岗位文本合规提示</h2><ul>{compliance}</ul>
<h2>安全审计</h2><p class="muted">被隔离的内容未进入岗位匹配或可选模型输入。</p><ul>{findings}</ul>
<h2>处理提醒</h2><ul>{warnings}</ul>
<p class="muted">引擎 {report.audit.engine_version} · 策略 {report.audit.policy_version} · {report.audit.created_at}</p>
</main></body></html>"""


def write_report(
    report: ReviewReport, path: str | Path, output_format: str | None = None
) -> Path:
    destination = Path(path)
    format_name = (output_format or destination.suffix.lstrip(".") or "json").lower()
    renderers = {"json": render_json, "csv": render_csv, "html": render_html}
    if format_name not in renderers:
        raise ValueError("输出格式仅支持 json、csv 或 html。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(renderers[format_name](report), encoding="utf-8")
    return destination
