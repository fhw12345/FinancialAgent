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
