---
title: Green Tests Hid a Broken Shared-Data Contract
status: shipped
version: backend@0.51.1, frontend@0.32.2
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/src/services/insights/snapshot_service.py
  - backend/src/services/data_manager/manager.py
  - frontend/src/components/chat/ChatMessages.tsx
  - docker-compose.yml
---

# Green Tests Hid a Broken Shared-Data Contract

> **TL;DR (EN)**: Nearly two thousand passing backend tests did not catch an
> invalid keyword between InsightsSnapshotService and DataManager because mocks
> accepted the call and a broad exception converted the programming error into
> ordinary provider degradation. A project-wide review repaired the contract,
> hardened local network and Markdown trust boundaries, and added browser proof.
>
> **TL;DR (中文)**：接近两千个后端测试全部通过，但 InsightsSnapshotService 与
> DataManager 之间的错误参数仍未被发现，因为 Mock 接受了调用，而宽泛异常处理又把
> 编程错误伪装成普通数据源降级。全项目审查随后修复了契约，并加固了本地网络和
> Markdown 信任边界，补充了真实浏览器证据。

## 1. Context

项目已经有大量单元测试、Agent golden eval 和 Playwright 场景，但全项目 review
仍发现运行边界、类型门禁和组合覆盖之间存在落差。最明确的例子出现在 Insights
刷新路径：设计要求一次共享预取取得股票、国债、新闻和 IPO 数据。

## 2. Investigation

静态类型检查报告调用端传入 `indicators=`，而真实 DataManager 方法只接受
`treasury_maturities=`。单元测试把 `prefetch_shared` 替换为 `AsyncMock`，只断言它
“被调用过”，没有验证真实签名和完整参数。

运行时的 `TypeError` 又被 `except Exception` 捕获并转换为 `{}`。因此页面可能仍然
显示结果，但共享预取从未执行，日志只表现为可恢复的数据源问题。

同一次 review 还发现两个类似的信任边界误差：Compose 的短端口语法把无认证服务
发布到所有主机接口；聊天 UI 允许 LLM 输出经过 raw HTML 解析。

## 3. Root Cause

根因不是缺少测试数量，而是测试边界选择错误：

1. Mock 替代了本应被验证的内部契约；
2. 宽泛异常处理没有区分 provider failure 和 programming error；
3. “本地运行”和“React 会转义内容”等假设没有通过部署配置和浏览器 DOM 验证；
4. CI 没有执行项目文档声称必须通过的全部门禁。

## 4. Fix

- 使用 `treasury_maturities=["2y", "10y"]` 调用真实契约；
- 由 `SharedDataContext.errors` 表达 provider 局部失败，不再吞掉调用错误；
- 测试精确验证 awaited arguments，并验证 `TypeError` 会向上传播；
- 所有 Compose 发布端口默认绑定 `127.0.0.1`；
- 移除 assistant Markdown 的 raw HTML 解析；
- 将前后端版本显示在 Health 页面，避免旧镜像 metadata 掩盖当前源码版本；
- 新增四个 project-hardening Playwright 场景和 curated screenshots。

## 5. Lessons

- 内部模块边界应尽量使用真实对象，只在网络、模型和 provider 外边界使用 fake。
- Graceful degradation 只能捕获预期运行故障，不能吞掉 `TypeError` 等编程错误。
- CORS 不是本地数据库或无认证 API 的访问控制。
- LLM 输出属于不可信输入，即使它由自己的模型生成。
- 总测试数和 aggregate coverage 不能替代关键路径的组合不变量。
- 版本、部署端口和浏览器 DOM 都需要可执行契约，而不能只依靠文档描述。
