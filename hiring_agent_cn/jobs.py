"""Mainland-China job description parsing and fairness warnings."""

from __future__ import annotations

import hashlib
import re

from .schemas import ComplianceFinding, JobProfile, JobRequirement
from .security import normalize_untrusted_text

COMPLIANCE_RULES: tuple[dict[str, object], ...] = (
    {
        "id": "CN-JD-GENDER",
        "category": "性别限制",
        "severity": "high",
        "pattern": re.compile(
            r"(?:仅限|限|只招|优先考虑)?\s*(?:男性|女性|男生|女生|男士|女士)(?:优先|候选人)?"
        ),
        "explanation": "岗位文本包含性别导向条件。除法律规定的特殊岗位外，这可能造成不平等就业条件。",
        "suggestion": "删除性别要求，改写为与岗位实际职责直接相关的能力或工作条件。",
    },
    {
        "id": "CN-JD-AGE",
        "category": "年龄门槛",
        "severity": "high",
        "pattern": re.compile(
            r"(?:年龄)?\s*(?:不超过|不满|低于|小于|限|以下)\s*\d{2}\s*岁|\d{2}\s*岁\s*(?:以下|以内)"
        ),
        "explanation": "岗位文本包含明确年龄门槛，可能与实际履职能力无直接关系。",
        "suggestion": "改为经验、技能、工作强度或法定资质等可验证条件。",
    },
    {
        "id": "CN-JD-MARITAL",
        "category": "婚育条件",
        "severity": "critical",
        "pattern": re.compile(r"(?:未婚|已婚已育|婚育|生育计划|暂无生育计划)"),
        "explanation": "婚姻或生育状况不是一般岗位的胜任证据。",
        "suggestion": "删除婚育条件，不在简历审阅或面试中采集和使用。",
    },
    {
        "id": "CN-JD-HOUSEHOLD",
        "category": "户籍地域限制",
        "severity": "high",
        "pattern": re.compile(
            r"(?:本地|当地|北京|上海|广州|深圳)?\s*(?:户口|户籍)(?:优先|限定|要求)?|本地人优先"
        ),
        "explanation": "户籍或籍贯通常不是岗位能力证据，可能形成不合理的人力资源流动限制。",
        "suggestion": "如确有到岗要求，只保留办公地点、出差频率或到岗时间。",
    },
    {
        "id": "CN-JD-HEALTH",
        "category": "健康信息",
        "severity": "high",
        "pattern": re.compile(r"(?:乙肝|无传染病|体检正常|身体健康证明)"),
        "explanation": "健康信息属于高风险个人信息，不应被泛化为普通筛选条件。",
        "suggestion": "仅在法律允许且与岗位必要性直接相关时，由合规流程单独处理。",
    },
    {
        "id": "CN-JD-APPEARANCE",
        "category": "外貌身体条件",
        "severity": "medium",
        "pattern": re.compile(r"(?:形象气质佳|五官端正|身高\s*\d{3}|颜值|长相)"),
        "explanation": "外貌或身体条件可能不是岗位胜任所必需。",
        "suggestion": "改写为具体服务场景、沟通职责或必要的职业要求。",
    },
    {
        "id": "CN-JD-SCHOOL-PRESTIGE",
        "category": "院校标签",
        "severity": "medium",
        "pattern": re.compile(
            r"(?:985|211|双一流|QS\s*(?:前|TOP)\s*\d+|名校)(?:院校|高校|毕业)?(?:优先|限定|要求)?",
            re.I,
        ),
        "explanation": "院校标签容易成为能力的替代变量，需确认其与实际岗位要求的必要性。",
        "suggestion": "优先使用专业知识、项目复杂度、作品或工作成果等直接证据。",
    },
)

TECH_TERMS = (
    "Python",
    "Java",
    "Go",
    "Golang",
    "C++",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Node.js",
    "Spring",
    "Django",
    "FastAPI",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "Kafka",
    "Docker",
    "Kubernetes",
    "Linux",
    "Git",
    "机器学习",
    "深度学习",
    "大模型",
    "LLM",
    "RAG",
    "数据分析",
    "产品设计",
    "项目管理",
    "销售",
    "客户成功",
    "招聘",
    "财务",
    "法务",
    "英语",
)
DOMAIN_TERMS = (
    "后端服务",
    "接口设计",
    "数据模型",
    "性能优化",
    "生产环境",
    "消息队列",
    "系统稳定性",
    "业务结果",
    "容器化",
    "容量",
    "设计",
    "开发",
    "上线",
)
STOPWORDS = {
    "负责",
    "熟悉",
    "掌握",
    "具备",
    "能够",
    "优先",
    "要求",
    "相关",
    "工作",
    "经验",
    "能力",
    "以上",
    "岗位",
    "参与",
    "完成",
    "以及",
}


def audit_job_description(text: str) -> list[ComplianceFinding]:
    normalized = normalize_untrusted_text(text)
    findings: list[ComplianceFinding] = []
    for rule in COMPLIANCE_RULES:
        pattern = rule["pattern"]
        assert isinstance(pattern, re.Pattern)
        for match in pattern.finditer(normalized):
            findings.append(
                ComplianceFinding(
                    rule_id=str(rule["id"]),
                    category=str(rule["category"]),
                    severity=rule["severity"],  # type: ignore[arg-type]
                    matched_text=match.group(0),
                    explanation=str(rule["explanation"]),
                    suggestion=str(rule["suggestion"]),
                )
            )
    return findings


def extract_keywords(text: str) -> list[str]:
    normalized = normalize_untrusted_text(text)
    found = [
        term
        for term in (*TECH_TERMS, *DOMAIN_TERMS)
        if re.search(re.escape(term), normalized, re.IGNORECASE)
    ]
    chunks = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,24}", normalized)
    for chunk in chunks:
        if chunk.lower() in {word.lower() for word in STOPWORDS}:
            continue
        if chunk not in found:
            found.append(chunk)
    return found[:12]


def _split_requirement_lines(text: str) -> list[str]:
    text = text.replace("；", "\n").replace(";", "\n")
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•·]|\d+[.、)]|[一二三四五六七八九十]+[、.])\s*", "", raw)
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = normalize_untrusted_text(line)
        if len(line) >= 4:
            lines.append(line)
    return lines


def parse_job_description(text: str, title: str | None = None) -> JobProfile:
    normalized = normalize_untrusted_text(text)
    if not normalized:
        raise ValueError("岗位说明不能为空。")
    raw_lines = _split_requirement_lines(text)
    inferred_title = title or (raw_lines[0][:60] if raw_lines else "未命名岗位")
    requirements: list[JobRequirement] = []
    seen: set[str] = set()
    for index, line in enumerate(raw_lines):
        if line == inferred_title and index == 0:
            continue
        if line in seen:
            continue
        seen.add(line)
        if re.search(r"(?:加分|优先|更佳|preferred|nice[ -]to[ -]have)", line, re.I):
            priority = "preferred"
        elif re.search(r"(?:职责|负责|参与|工作内容|responsibilit)", line, re.I):
            priority = "responsibility"
        else:
            priority = "must"
        if re.search(r"(?:学历|本科|硕士|博士|专业|毕业)", line):
            category = "教育与资质"
        elif re.search(r"(?:年经验|技术|开发|工程|算法|数据|Python|Java|Go|C\+\+)", line, re.I):
            category = "专业能力"
        elif priority == "responsibility":
            category = "岗位职责"
        else:
            category = "通用能力"
        digest = hashlib.sha256(f"{index}|{line}".encode()).hexdigest()[:10]
        requirements.append(
            JobRequirement(
                requirement_id=f"REQ-{digest}",
                text=line,
                priority=priority,  # type: ignore[arg-type]
                category=category,
                keywords=extract_keywords(line),
            )
        )
    if not requirements:
        raise ValueError("未能从岗位说明中识别出可审阅的要求。请使用分行或列表描述。")
    return JobProfile(
        title=inferred_title,
        raw_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        requirements=requirements,
        compliance_findings=audit_job_description(text),
    )
