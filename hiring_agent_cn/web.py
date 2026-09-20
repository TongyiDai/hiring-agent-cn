"""Small local-first FastAPI UI. No files are persisted by the server."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from .human_review import apply_human_review
from .render import render_html
from .review import ReviewEngine
from .schemas import HumanReviewAction, ReviewReport

app = FastAPI(
    title="Hiring Agent CN",
    version="1.0.0",
    description="面向人工复核的人岗证据审阅 API，不提供自动淘汰端点。",
)

INDEX_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>人岗证据审阅</title><style>
:root{--b:#2f6bff;--i:#111827;--m:#667085;--l:#dfe3eb}*{box-sizing:border-box}body{margin:0;background:#f7f8fb;color:var(--i);font:16px/1.6 system-ui,-apple-system,"PingFang SC",sans-serif}main{max-width:900px;margin:auto;padding:56px 24px}h1{font-size:42px;line-height:1.15;margin:0}.lead{color:var(--m);font-size:18px}.box{background:#fff;border:1px solid var(--l);border-radius:16px;padding:24px;margin-top:28px}label{display:block;font-weight:650;margin:16px 0 6px}input,textarea{width:100%;padding:12px;border:1px solid var(--l);border-radius:8px;font:inherit}textarea{min-height:260px}button{margin-top:22px;background:var(--b);color:white;border:0;border-radius:8px;padding:12px 22px;font:inherit;font-weight:650;cursor:pointer}.note{border-left:4px solid var(--b);padding-left:14px;color:var(--m)}#state{margin-left:12px;color:var(--m)}
</style></head><body><main><h1>先看证据，再做判断</h1><p class="lead">隔离隐藏文本与提示注入，生成可追溯的人岗证据矩阵。</p><p class="note">本工具不自动录用或淘汰候选人。文件仅在本次请求中处理，默认不持久化。</p><form class="box" id="form"><label>候选人材料</label><input name="resume" type="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg" required><label>岗位名称</label><input name="job_title" placeholder="例如：后端工程师"><label>岗位说明</label><textarea name="job_text" placeholder="粘贴岗位职责与任职要求，每条一行" required></textarea><label><input name="confirm_job_profile" type="checkbox" value="true" style="width:auto" required> 我已人工核对岗位要求及公平招聘风险提示</label><button>开始审阅</button><span id="state"></span></form></main><script>document.getElementById('form').addEventListener('submit',async(e)=>{e.preventDefault();const s=document.getElementById('state');s.textContent='正在本机处理…';const r=await fetch('/review/html',{method:'POST',body:new FormData(e.target)});if(!r.ok){s.textContent='处理失败：'+await r.text();return}document.open();document.write(await r.text());document.close()})</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return INDEX_HTML


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "decision_mode": "human-review-required"}


def _run_upload(
    upload: UploadFile,
    job_text: str,
    job_title: str | None,
    confirm_job_profile: bool,
):
    suffix = Path(upload.filename or "resume.pdf").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(status_code=415, detail="不支持的文件格式。")
    content = upload.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 10MB。")
    descriptor, raw_path = tempfile.mkstemp(prefix="hiring-agent-cn-", suffix=suffix)
    os.close(descriptor)
    temp_path = Path(raw_path)
    try:
        temp_path.write_bytes(content)
        return ReviewEngine().review(
            temp_path,
            job_text,
            job_title=job_title,
            confirm_job_profile=confirm_job_profile,
        )
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/review")
def api_review(
    resume: Annotated[UploadFile, File()],
    job_text: Annotated[str, Form()],
    job_title: Annotated[str | None, Form()] = None,
    confirm_job_profile: Annotated[bool, Form()] = False,
) -> JSONResponse:
    try:
        report = _run_upload(resume, job_text, job_title, confirm_job_profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(report.model_dump(mode="json"))


@app.post("/review/html", response_class=HTMLResponse)
def html_review(
    resume: Annotated[UploadFile, File()],
    job_text: Annotated[str, Form()],
    job_title: Annotated[str | None, Form()] = None,
    confirm_job_profile: Annotated[bool, Form()] = False,
) -> str:
    try:
        return render_html(_run_upload(resume, job_text, job_title, confirm_job_profile))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/sign-off")
def api_sign_off(
    report: ReviewReport, actions: list[HumanReviewAction], reviewer_id: str
) -> JSONResponse:
    """Record review decisions; deliberately no reject/advance endpoint exists."""
    try:
        signed = apply_human_review(report, actions, reviewer_id=reviewer_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(signed.model_dump(mode="json"))
