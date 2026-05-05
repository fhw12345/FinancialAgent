# Interview Case Studies

本目录收录开发过程中遇到的有教学价值的 bug / 设计决策 / 调试故事，用于面试 prep。

每篇按统一结构：背景 → 思考过程 → 根因 → 解决方案 → 教训。
重点是**思考过程**——展示假设、验证、走过的弯路，不只是最终修复。

## Index

| Date | Title | Component | Topic |
|------|-------|-----------|-------|
| 2026-05-04 | [Ghost Compose Project](2026-05-04-ghost-compose-project.md) | Docker | 同名 compose 项目互撞 + Windows bind mount 静默建空目录 |
| 2026-05-04 | [Token 统计永远是 0](2026-05-04-token-extraction-getattr-on-dict.md) | LangChain / 测试 | `getattr` 用在 dict 上 + `Mock` 遮蔽真实数据形状 |
| 2026-05-04 | [Finnhub fallback chain](2026-05-04-finnhub-fallback-chain.md) | 服务层架构 | 三层 fallback + "注释撒谎"模式 + Mock 兜底盲点 |
| 2026-05-04 | [Decision tracking cross-layer](2026-05-04-decision-tracking-cross-layer.md) | 端到端 | 5 层 instrumentation + 端口陷阱（同一根因家族第二次）|
| 2026-05-05 | [翻译管道多层根因](2026-05-05-translation-pipeline-multilayer.md) | 前端 i18n + LLM | React Query 缓存命中 vs isLoading 背离 + max_tokens 静默截断 + raw md 渲染漏 |
| 2026-05-05 | [SELL 平多仓 prompt 语义](2026-05-05-sell-close-long-prompt-semantics.md) | LLM prompt | BUY/SELL 共用 schema 字段反向语义 + reasoning cite 范围模糊 |
| 2026-05-06 | [Vite + Docker Windows HMR 静默失效](2026-05-06-vite-docker-hmr-silent-failure.md) | Vite / Docker / inotify | bind mount 传内容不传事件 + 好习惯掩盖 bug N 周 |
