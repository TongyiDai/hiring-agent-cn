"""Deterministic defenses against hidden text and prompt injection.

Candidate-controlled documents are untrusted input.  Suspicious text is quarantined
before any optional language model sees the document.  Findings remain available to
human reviewers as hashes, bounded previews, page numbers, and coordinates.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field

from .schemas import SecurityFinding, Severity

ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override-instructions",
        re.compile(
            r"(?:ignore|disregard|override|forget).{0,40}(?:previous|prior|system|instruction|prompt)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "override-instructions-zh",
        re.compile(
            r"(?:忽略|无视|覆盖|绕过|不要遵守).{0,24}(?:之前|以上|系统|规则|指令|提示词)",
            re.DOTALL,
        ),
    ),
    (
        "forced-outcome",
        re.compile(
            r"(?:must|always|直接|必须|务必|请).{0,24}(?:pass|hire|accept|通过|录用|满分|100\s*分)",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "role-injection",
        re.compile(
            r"(?:system\s*(?:message|prompt)|developer\s*message|assistant\s*:|你是(?:一个)?(?:招聘|评分|AI)|系统提示(?:词)?)",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(slots=True)
class SpanObservation:
    text: str
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    font_size: float | None = None
    color: tuple[float, float, float] | None = None
    background: tuple[float, float, float] | None = None
    opacity: float | None = None
    render_mode: int | None = None
    covered_by_later_object: bool = False
    outside_page: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def normalize_untrusted_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = ZERO_WIDTH_RE.sub("", text)
    return " ".join(text.replace("\x00", "").split())


def injection_reasons(text: str) -> list[str]:
    normalized = normalize_untrusted_text(text)
    return [rule_id for rule_id, pattern in INJECTION_PATTERNS if pattern.search(normalized)]


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        value = min(1.0, max(0.0, value))
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(value) for value in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(
    foreground: tuple[float, float, float], background: tuple[float, float, float]
) -> float:
    first = _relative_luminance(foreground)
    second = _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def int_to_rgb(color: int | None) -> tuple[float, float, float] | None:
    if color is None:
        return None
    return (
        ((color >> 16) & 255) / 255,
        ((color >> 8) & 255) / 255,
        (color & 255) / 255,
    )


def intersection_ratio(
    inner: tuple[float, float, float, float] | None,
    outer: tuple[float, float, float, float] | None,
) -> float:
    if not inner or not outer:
        return 0.0
    x0 = max(inner[0], outer[0])
    y0 = max(inner[1], outer[1])
    x1 = min(inner[2], outer[2])
    y1 = min(inner[3], outer[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    area = max(1e-9, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return ((x1 - x0) * (y1 - y0)) / area


def assess_span(observation: SpanObservation) -> SecurityFinding | None:
    text = normalize_untrusted_text(observation.text)
    if not text:
        return None

    reasons: list[str] = []
    severity: Severity = "medium"

    if observation.opacity is not None and observation.opacity < 0.15:
        reasons.append("low-opacity-text")
        severity = "high"
    if observation.render_mode == 3:
        reasons.append("invisible-pdf-render-mode")
        severity = "critical"
    if observation.font_size is not None and observation.font_size < 3.0:
        reasons.append("micro-font")
        severity = "high"
    if observation.outside_page:
        reasons.append("outside-visible-page")
        severity = "high"
    if observation.covered_by_later_object:
        reasons.append("covered-by-later-object")
        severity = "high"
    if ZERO_WIDTH_RE.search(observation.text):
        reasons.append("unicode-control-characters")
    if observation.color and observation.background:
        ratio = contrast_ratio(observation.color, observation.background)
        if math.isfinite(ratio) and ratio < 1.35:
            reasons.append("low-contrast-text")
            severity = "high"

    prompt_reasons = injection_reasons(text)
    reasons.extend(prompt_reasons)
    if prompt_reasons:
        severity = "critical"

    if not reasons:
        return None

    digest = sha256_text(
        f"{observation.page_number}|{observation.bbox}|{text}|{'|'.join(reasons)}"
    )
    preview = text[:96] + ("…" if len(text) > 96 else "")
    return SecurityFinding(
        finding_id=f"SEC-{digest[:12]}",
        kind=reasons[0],
        severity=severity,
        page_number=observation.page_number,
        bbox=observation.bbox,
        text_sha256=sha256_text(text),
        text_preview=preview,
        reasons=sorted(set(reasons)),
        action="quarantined",
    )


def strip_instruction_like_content(text: str) -> tuple[str, list[str]]:
    """Remove instruction-like lines from non-document enrichment sources."""
    safe_lines: list[str] = []
    removed: list[str] = []
    for raw_line in (text or "").splitlines():
        line = normalize_untrusted_text(raw_line)
        if not line:
            continue
        if injection_reasons(line):
            removed.append(sha256_text(line))
        else:
            safe_lines.append(line)
    return "\n".join(safe_lines), removed
