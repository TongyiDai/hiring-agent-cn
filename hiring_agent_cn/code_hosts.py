"""Opt-in public-code evidence adapters for GitHub, Gitee, and GitCode."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from .schemas import CodeEvidence
from .security import strip_instruction_like_content


@dataclass(frozen=True, slots=True)
class ParsedCodeURL:
    platform: str
    owner: str
    repository: str | None
    url: str


def parse_code_url(url: str) -> ParsedCodeURL | None:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        return None
    host = parsed.netloc.lower().removeprefix("www.")
    platform = {
        "github.com": "github",
        "gitee.com": "gitee",
        "gitcode.com": "gitcode",
    }.get(host)
    if not platform:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    return ParsedCodeURL(
        platform=platform,
        owner=parts[0],
        repository=parts[1].removesuffix(".git") if len(parts) > 1 else None,
        url=url,
    )


def _safe_summary(parts: list[str | None]) -> tuple[str, str | None]:
    safe, hashes = strip_instruction_like_content("\n".join(part for part in parts if part))
    warning = None
    if hashes:
        warning = f"远端简介中有 {len(hashes)} 行疑似提示注入，已隔离。"
    return safe[:1200], warning


def _request_json(
    url: str, *, headers: dict[str, str] | None = None, params: dict[str, str] | None = None
) -> object:
    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _github_evidence(target: ParsedCodeURL) -> CodeEvidence:
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if target.repository:
        payload = _request_json(
            f"https://api.github.com/repos/{target.owner}/{target.repository}",
            headers=headers,
        )
        assert isinstance(payload, dict)
        summary, warning = _safe_summary(
            [str(payload.get("name") or ""), str(payload.get("description") or "")]
        )
        metrics = {
            "stars": int(payload.get("stargazers_count") or 0),
            "forks": int(payload.get("forks_count") or 0),
            "open_issues": int(payload.get("open_issues_count") or 0),
            "language": payload.get("language"),
            "updated_at": payload.get("updated_at"),
        }
    else:
        profile = _request_json(f"https://api.github.com/users/{target.owner}", headers=headers)
        repos = _request_json(
            f"https://api.github.com/users/{target.owner}/repos",
            headers=headers,
            params={"per_page": "100", "sort": "updated"},
        )
        assert isinstance(profile, dict) and isinstance(repos, list)
        summary, warning = _safe_summary(
            [
                str(profile.get("bio") or ""),
                *(
                    str(repo.get("description") or "")
                    for repo in repos[:20]
                    if isinstance(repo, dict)
                ),
            ]
        )
        metrics = {
            "public_repos": int(profile.get("public_repos") or 0),
            "followers": int(profile.get("followers") or 0),
            "recent_repositories_checked": len(repos[:20]),
        }
    return CodeEvidence(
        platform="GitHub",
        url=target.url,
        verified=True,
        summary=summary,
        metrics=metrics,
        warning=warning,
    )


def _gitee_like_evidence(target: ParsedCodeURL) -> CodeEvidence:
    is_gitcode = target.platform == "gitcode"
    token_name = "GITCODE_TOKEN" if is_gitcode else "GITEE_TOKEN"
    token = os.getenv(token_name)
    if not token:
        return CodeEvidence(
            platform="GitCode" if is_gitcode else "Gitee",
            url=target.url,
            verified=False,
            summary="未调用平台 API；仓库链接仅作为候选人提供的待核验材料。",
            warning=f"如需核验公开仓库元数据，请设置 {token_name}。",
        )
    base = "https://api.gitcode.com/api/v5" if is_gitcode else "https://gitee.com/api/v5"
    if target.repository:
        payload = _request_json(
            f"{base}/repos/{target.owner}/{target.repository}", params={"access_token": token}
        )
        items = [payload]
    else:
        payload = _request_json(
            f"{base}/users/{target.owner}/repos",
            params={"access_token": token, "per_page": "50", "sort": "updated"},
        )
        items = payload if isinstance(payload, list) else []
    safe_items = [item for item in items if isinstance(item, dict)]
    summary, warning = _safe_summary(
        [str(item.get("description") or "") for item in safe_items]
    )
    return CodeEvidence(
        platform="GitCode" if is_gitcode else "Gitee",
        url=target.url,
        verified=True,
        summary=summary,
        metrics={"repositories_checked": len(safe_items)},
        warning=warning,
    )


def collect_code_evidence(urls: list[str]) -> list[CodeEvidence]:
    evidence: list[CodeEvidence] = []
    for url in urls:
        target = parse_code_url(url)
        if not target:
            evidence.append(
                CodeEvidence(
                    platform="unsupported",
                    url=url,
                    verified=False,
                    summary="仅支持候选人主动提供的 GitHub、Gitee 或 GitCode 链接。",
                    warning="未访问该链接。",
                )
            )
            continue
        try:
            if target.platform == "github":
                evidence.append(_github_evidence(target))
            else:
                evidence.append(_gitee_like_evidence(target))
        except (requests.RequestException, ValueError, KeyError) as exc:
            evidence.append(
                CodeEvidence(
                    platform=target.platform.title(),
                    url=url,
                    verified=False,
                    summary="远端元数据核验失败，未将该链接用于判断。",
                    warning=type(exc).__name__,
                )
            )
    return evidence
