# 上游迁移说明

## 来源

- 上游：[`interviewstreet/hiring-agent`](https://github.com/interviewstreet/hiring-agent)
- 分叉基线：`70fd3ea9aa74d8f76519ec643a99f9871003e70d`
- 许可证：MIT，根目录 `LICENSE` 保留原版权声明。

## 为什么建立新内核

上游是一个小型、透明的简历评分原型，适合研究提示词和角色量表。但它的默认量表面向 HackerRank 软件实习生，以 GitHub 开源贡献为高权重信号；原始姓名、学校和位置仍进入模型；开发模式会明文缓存；主分支缺少测试、CI、Web/API 和完整安全控制。

Hiring Agent CN 没有直接翻译旧提示词，而是在 `hiring_agent_cn/` 中建立独立、安全的证据审阅内核。旧文件暂时保留用于来源追溯。

## 已吸收或规避的上游公开问题

- [#452](https://github.com/interviewstreet/hiring-agent/issues/452)：GitHub 内容提示注入。新适配器在证据进入匹配前过滤指令型行。
- [#431](https://github.com/interviewstreet/hiring-agent/issues/431)：同名 PDF 缓存冲突。新内核默认不缓存，以内容哈希标识输入。
- [#432](https://github.com/interviewstreet/hiring-agent/issues/432) / [#427](https://github.com/interviewstreet/hiring-agent/issues/427)：分数边界。新内核不生成脱离岗位的总分。
- [#400](https://github.com/interviewstreet/hiring-agent/issues/400)：多栏简历丢失内容。新内核保留页码/坐标，并对无可信文字的页面提供渲染 OCR 回退。
- [#409](https://github.com/interviewstreet/hiring-agent/issues/409)：开源经历丢失。新内核不设固定“开源分”，代码平台只是可选证据源。
- [#430](https://github.com/interviewstreet/hiring-agent/issues/430)：CSV 列错位。新导出使用固定字段并由测试覆盖。

## 同步策略

`upstream` remote 保持指向原项目。后续同步应优先挑选通用安全、解析和 provider 修复；不要直接合并会恢复总分淘汰、原始个人字段模型输入或默认明文缓存的变更。

如需研究旧入口，使用 `uv sync --extra legacy` 安装上游 PDF 转换依赖。旧入口的 `DEVELOPMENT_MODE` 已改为默认关闭，避免无意写入简历缓存与 CSV。
