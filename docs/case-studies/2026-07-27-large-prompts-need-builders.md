---
title: Large Prompts Need Builders
status: shipped
version: backend@0.47.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/portfolio_phase2_prompt.py
  - backend/src/agent/portfolio/phase2_decisions.py
---

# Large Prompts Need Builders

> **TL;DR (EN)**: The Portfolio decision prompt contained hundreds of lines of
> safety-critical rules and examples. Replacing it with a shorter registry
> summary would change behavior; registering the inline string would leave the
> registry detached. Extracting an exact renderer preserved the contract and
> reduced the execution module to 500 lines.
>
> **TL;DR (中文)**：Portfolio decision prompt 包含数百行安全规则和示例。
> 用简化 registry 文本会改变行为，只登记 inline string 又会脱离运行时。
> 最终通过等价 renderer 保留完整 contract，并将执行文件降到 500 行。

## Lesson

Large prompts are executable policy. Migrations should move their builder and
tests together rather than paraphrasing the text.
