"""Create a blind-review representation before matching or LLM analysis."""

from __future__ import annotations

import re

from .schemas import BlindResume, DocumentExtraction, EvidenceBlock, RedactionRecord
from .security import sha256_text

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("id_number", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
    ("email", re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("gender", re.compile(r"(?:性别|gender)\s*[:：]?\s*(?:男|女|male|female)", re.I)),
    (
        "birth_or_age",
        re.compile(
            r"(?:出生(?:年月|日期)?|年龄|age|birth(?:day|date)?)\s*[:：]?\s*[^,，;；\n]{1,20}",
            re.I,
        ),
    ),
    ("marital", re.compile(r"(?:婚姻|婚育|marital)\s*[:：]?\s*[^,，;；\n]{1,12}", re.I)),
    (
        "ethnicity",
        re.compile(r"(?:民族|ethnicity|religion|宗教)\s*[:：]?\s*[^,，;；\n]{1,16}", re.I),
    ),
    (
        "household",
        re.compile(r"(?:户籍|籍贯|住址|家庭地址|address)\s*[:：]?\s*[^,，;；\n]{1,40}", re.I),
    ),
    ("political_status", re.compile(r"(?:政治面貌)\s*[:：]?\s*[^,，;；\n]{1,16}")),
)

NAME_LABEL_RE = re.compile(
    r"(?:姓名|name)\s*[:：]\s*([\u4e00-\u9fff·]{2,8}|[A-Za-z][A-Za-z .'-]{1,50})",
    re.I,
)
CONTACT_HINT_RE = re.compile(r"(?:电话|手机|邮箱|email|phone|求职|应聘)", re.I)
NAME_ONLY_RE = re.compile(r"^(?:[\u4e00-\u9fff·]{2,6}|[A-Z][a-z]+(?: [A-Z][a-z]+){1,3})$")


def _replace(
    text: str, evidence_id: str, kind: str, pattern: re.Pattern[str]
) -> tuple[str, list[RedactionRecord]]:
    records: list[RedactionRecord] = []

    def substitute(match: re.Match[str]) -> str:
        value = match.group(0)
        placeholder = f"[已隔离:{kind}]"
        records.append(
            RedactionRecord(
                kind=kind,
                placeholder=placeholder,
                value_sha256=sha256_text(value),
                evidence_id=evidence_id,
            )
        )
        return placeholder

    return pattern.sub(substitute, text), records


class PrivacyRedactor:
    def redact(self, extraction: DocumentExtraction) -> BlindResume:
        blocks: list[EvidenceBlock] = []
        all_records: list[RedactionRecord] = []

        header_has_contact = any(
            CONTACT_HINT_RE.search(block.text) for block in extraction.blocks[:6]
        )

        for index, source in enumerate(extraction.blocks):
            text = source.text
            for kind, pattern in RULES:
                text, records = _replace(text, source.evidence_id, kind, pattern)
                all_records.extend(records)

            text, records = _replace(text, source.evidence_id, "name", NAME_LABEL_RE)
            all_records.extend(records)

            if index == 0 and header_has_contact and NAME_ONLY_RE.fullmatch(text.strip()):
                original = text.strip()
                text = "[已隔离:name]"
                all_records.append(
                    RedactionRecord(
                        kind="name",
                        placeholder="[已隔离:name]",
                        value_sha256=sha256_text(original),
                        evidence_id=source.evidence_id,
                    )
                )

            blocks.append(source.model_copy(update={"text": text}))

        return BlindResume(
            source_sha256=extraction.source_sha256,
            blocks=blocks,
            safe_text="\n".join(block.text for block in blocks if block.text.strip()),
            redactions=all_records,
        )
