# Contributing

感谢你帮助改进 Hiring Agent CN。这个项目处理的是高风险招聘场景，正确性、隐私和可审计性优先于功能数量。

## 开始前

1. 搜索现有 issue，避免重复工作。
2. 对大改动先开 issue，说明问题、威胁模型和验收方式。
3. 从 `main` 创建独立分支。
4. 不要提交真实简历、候选人姓名、手机号、邮箱、身份证号、内部 JD、面试反馈、API Key 或访问令牌。

## 开发环境

```bash
uv sync --extra dev --frozen
uv run ruff check hiring_agent_cn tests
uv run ruff format --check hiring_agent_cn tests
uv run mypy hiring_agent_cn
uv run pytest
```

OCR 是可选能力：

```bash
uv sync --extra dev --extra ocr
```

## 设计原则

- 候选人材料、岗位文本和外部平台内容均视为不可信输入。
- 可疑内容必须在模型调用前隔离，不能只靠 system prompt。
- 每条判断必须引用实际存在的 evidence ID。
- 模型不能把确定性结果从“尚未确认”提升为“有直接证据”。
- 没有证据只表示需要核验，不能解释为不具备。
- 新功能不得引入自动录用、自动淘汰或批量拒绝。
- 性别、年龄、婚育、民族、宗教、户籍、住址、健康等字段不得进入匹配。
- 默认本地处理；新外部传输必须显式配置并写清楚数据边界。

## 测试要求

解析或安全修复必须附最小合成样本。优先用测试代码现场生成 PDF/DOCX，而不是提交二进制简历。安全测试至少说明：

1. 攻击内容是什么；
2. 哪一层应当拦截；
3. 被隔离内容不会出现在 `safe_text`、证据引用和模型输入；
4. 检测失败时系统如何安全降级。

涉及匹配逻辑时，应同时加入反例，防止把“材料未写”判成“候选人不会”。

## 提交和 Pull Request

- 使用清晰、祈使语气的提交标题。
- PR 说明写清行为变化、测试证据、隐私影响和兼容性。
- 修改模型提示词时，必须附脱敏的前后对比与确定性边界。
- 修改依赖或外部 API 时，说明许可证、数据是否出境以及失败策略。

## 上游贡献

如果修复同样适用于原始 [interviewstreet/hiring-agent](https://github.com/interviewstreet/hiring-agent)，欢迎将最小、通用的修复另行贡献给上游。本项目特有的中国大陆合规和产品边界可以保留在本 fork。
