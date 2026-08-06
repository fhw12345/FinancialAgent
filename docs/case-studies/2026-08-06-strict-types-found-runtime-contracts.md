---
title: Strict Types Found Runtime Contract Failures
status: shipped
version: backend@0.51.2
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/pyproject.toml
  - backend/src/services/data_manager/manager.py
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/agent/portfolio/
---

# Strict Types Found Runtime Contract Failures

> **TL;DR (EN)**: Strict mypy initially reported 297 errors, but several were
> real runtime hazards rather than annotation noise: heterogeneous gathered
> exceptions were consumed as data, invalid cache shapes reached dataclass
> constructors, optional services were dereferenced, and local single-user
> models were still checked as if they carried removed ownership fields. The
> pass reached zero errors without disabling strictness and added CI enforcement.
>
> **TL;DR (中文)**：严格 mypy 最初报告 297 个错误，其中不少并非注解噪声，而是
> 真实运行风险：异构 `gather` 异常被当作数据消费、无效缓存结构进入 dataclass
> 构造器、可选服务被直接解引用，以及本地单用户模型仍按已移除的所有权字段检查。
> 本次治理没有关闭 strict，最终达到零错误并接入 CI。

## 1. Context

项目规范长期声明 mypy 必须零错误，但 PR CI 实际没有运行 mypy。随着单用户化、
DataManager fallback、Portfolio mixin 和 LangGraph API 演进，类型契约逐渐漂移到
297 个错误、81 个文件。

## 2. Investigation

错误按风险排序处理，而不是先批量添加 ignore：

1. model/repository 和 provider payload 契约；
2. `asyncio.gather(return_exceptions=True)` 的 BaseException 分支；
3. Optional service、analyzer、snapshot composite；
4. cache JSON shape 和 dataclass deserialization；
5. Portfolio mixin 的依赖属性；
6. 裸泛型、缺失函数注解和第三方 stub。

Pydantic mypy plugin 立即消除了一批错误，也暴露了项目源码 metadata 与旧安装包
之间的差异。全量测试还证明某些看似“所有权校验”的 `holding.user_id` 已不属于
本地单用户模型，不能通过伪造字段解决。

## 3. Root Cause

- CI 与本地文档门禁不一致；
- 内部边界使用 Any 和 Mock，真实返回 shape 没有被缩窄；
- fallback 代码把 provider、cancellation 和 programming failure 混为一类；
- mixin 通过运行时组合获得属性，却没有声明静态依赖；
- 单用户迁移删除了字段，但部分 service 仍保留旧调用假设。

## 4. Fix

- 启用 `pydantic.mypy` 并保留所有 strict 选项；
- 所有 Motor、集合、Callable 和 Queue 泛型显式参数化；
- 缓存和 provider 数据先做 shape validation，再构造 domain dataclass；
- gathered cancellation 重新抛出，其他 BaseException 记录为任务失败；
- Portfolio mixin 明确声明 repository、agent、settings 和 optimizer 依赖；
- 缺少 DataManager、composite、avg_price 等必要值时快速失败；
- 本地 holding 更新/删除只验证记录存在，不再访问不存在的多用户字段；
- PR CI 执行与本地相同的 `python -m mypy src/`。

实现提交：`6344fd4`。

## 5. Lessons

- “类型错误”常常是被宽泛 fallback 隐藏的运行时错误。
- `return_exceptions=True` 的结果类型包含 `BaseException`，只判断
  `Exception` 不足以安全缩窄。
- 缓存命中不是数据可信的证明，反序列化边界仍必须验证 shape。
- mixin 若没有显式依赖契约，会把初始化顺序问题留到运行时。
- 架构迁移必须同时删除旧字段假设，不能依赖框架忽略额外参数。
- 类型门禁只有在 CI 中执行才是真正的门禁。
