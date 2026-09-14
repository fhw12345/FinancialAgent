---
title: Multidimensional Insights Risk and Honest Missing Data
status: planning
version: n/a
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - backend/src/services/insights/categories/ai_sector_risk.py
  - backend/src/services/insights/base.py
  - backend/src/services/insights/models.py
  - backend/src/services/insights/snapshot_service.py
  - backend/src/api/schemas/insights_models.py
  - frontend/src/components/insights/
---

# IDQ-007：多维风险诊断与缺数据语义

## 1. 根因与目标

[总计划](investment-decision-quality-program.md) 的Insights工作包。现有AI分数把
情绪过热、融资压力、利率变化等合成一个0–100值，并给出建仓/减仓文案。不同维度
并非同一经济变量；缺数用50等占位不等于中性，`score=-1`的错误路径还与score≥0的
schema不一致。

目标：先保证数据状态真实，再拆分经济含义；未经验证不把分数映射成交易指令。
不声称纠正一个RRP符号就能预测市场，也不把当前成分股历史回填成无偏AI指数。

可先独立实现missing-data止血；完整引用依赖
[004](investment-evidence-snapshots.md)，策略映射依赖005和009的研究结果。

## 2. 新的风险维度（方法候选，不是已验证因子）

| 维度 | 可研究的输入 | 不能直接推导 |
| --- | --- | --- |
| valuation/crowding | 估值分位、价格偏离、情绪、期权拥挤 | 高分=马上下跌；低分=安全买入 |
| trend/breadth | 趋势、板块广度、分散程度 | 强趋势一定泡沫或一定继续涨 |
| funding/liquidity stress | SOFR/EFFR、RRP与其他流动性背景 | 单一RRP余额=股票可用资金 |
| earnings/macro deterioration | 盈利修订、现金流、经济/利率背景 | 收益率下降只能是风险偏好上升 |
| data quality | coverage、freshness、conflict、PIT支持 | 缺数据=中性50或低风险 |

需要的输入当前无法获得时，先显示unavailable，不为了填满维度再造指标。跨维度
聚合若尚无验证，v1不提供新的“总买卖分数”。现有指标可展示raw values及方法限制。

## 3. 数据与API契约（拟定 v2）

`RiskDimension`含dimension_id/method_version、value（可null）、unit、
`state=available|partial|unavailable|conflicting`、evidence IDs、coverage、freshness、
interpretation、limitations。数值分位/heuristic必须区分，不是回撤概率。

- 缺值只用null+状态；不能用50、62、-1等普通数字代替。
- coverage按预先定义的expected inputs计算，分子/分母都暴露；显示缺失来源清单。
- 可用维度也不能掩盖另一个关键维度缺失。没有完整方法支持时不计算combined risk。
- 若保留某个维度内部的加权值，必须记录所用权重、有效coverage及方法版本；缺项时
  不静默重归一化，partial分数不能冒充完整分数并进入001。
- 时间展示区分data as_of与refreshed_at；provider延迟/非交易日不伪装成新数据。
- 解释只描述可观察事实和限制；删除“正常分数说明健康牛市”“低分历史上适合建仓”等
  没有本仓库统计证据支撑的固定结论。

### 与现有刷新／历史契约协调

- 新响应显式schema_version=2，frontend/backend同步实现并做兼容契约测试。
- `create_snapshot`当前要求非空composite，实施时必须改为理解dimension结果；全部缺数
  是合法的unavailable结果，不是假成功的正常指数，也不必产生数值校验异常。
- 保存失败仍是运行失败，不能将“数据不可用”和“数据库写失败”混成一种状态。
- 历史v1快照保留旧数值与method version，标legacy heuristic，禁止重标为新方法。
- v1/v2趋势分段，不跨方法版本直接连成一条可比较曲线。旧reader只读旧快照；不通过
  给v2补假数字适配旧schema。切换/不支持版本的响应必须明确，不能白屏。

## 4. 金融假设与验证纪律

- RRP要结合货币基金配置、财政/准备金和政策背景解释；不预设永久单调方向。
- funding spread上升可以表示压力增加，即使泡沫形成条件减少，也不能降低“下跌风险”
  的展示语义。过热与压力必须允许同时高、同时低或方向不同。
- 2Y yield变化区分通胀/增长/政策解释，不把风险偏好路径写死。
- 新闻来源去重、PCR口径和样本组成必须固定，避免一个事件反复计数。
- AIQ动态basket的时点membership与权重保存；历史分析不能偷用今天的赢家名单。
- 任何新增经济权重、阈值、分位窗口都进入method spec；由009做out-of-sample验证。
  不在同一历史样本挑最漂亮的权重后叫有效指标。

## 5. 实施步骤

- [ ] 先做缺provider、空DataFrame、NaN和全部缺数的失败测试。
- [ ] 建nullable value/state DTO和v1/v2历史适配。
- [ ] 拆metric calculation与interpretation，去掉占位分和自动交易文案。
- [ ] 接004证据、时间与coverage；保留PH-002 request-local共享输入与provider调用计数。
- [ ] 新维度UI显示raw values/状态/方法限制与历史分段。
- [ ] 记录方法假设，待009验证后再提议任何交易映射。

## 6. 验证矩阵

拟新增 `test_insight_risk_dimensions.py`、`test_insight_missing_data_contract.py`、
`test_insight_method_history.py`。

| ID | Fixture | Oracle |
| --- | --- | --- |
| IR-01 | FRED/news/price各自缺失与全部缺失 | value=null或明确partial；无50/62占位、无-1校验冲突 |
| IR-02 | 所有维度无有效数据 | unavailable可持久化/读取；不显示normal/low-risk |
| IR-03 | funding压力上升、价格情绪下降 | 两维度独立呈现；不合成“更适合买入” |
| IR-04 | 相同2Y变化、不同增长情景 | 原始事实相同，条件解释可不同，不输出唯一风险偏好结论 |
| IR-05 | 某高风险维度missing | 覆盖率下降可见；不能靠缺项变成低总风险 |
| IR-06 | v1历史与v2新结果共存 | 旧值不变；UI按method分段，不拼接成同口径趋势 |
| IR-07 | provider恢复后刷新 | 新snapshot变available；旧unavailable不被重写 |
| IR-08 | Mongo失败／Redis失败／重复刷新 | 保存失败不报成功；重试幂等与PH-002共享调用契约保留 |
| IR-09 | membership变化与转载重复新闻 | 成分版本可追溯；独立事件不重复计数 |
| IR-10 | API存在partial/null、翻译/刷新/reload | 前端不把null转0、50、绿灯或NaN |

### Playwright

拟新增 `frontend/e2e/idq-insights-dimensions.spec.ts`：

- `idq-007-missing-is-unknown`：可见刷新，录制FRED缺数；显示数据不足及coverage，而非
  中性正常分；真实API/Mongo同样null/state。截图 `assets/idq-007/01-unavailable-risk.png`。
- `idq-007-independent-dimensions`：压力高/拥挤度低的fixture同时可见；无自动建仓文案；
  历史v1切换不连错曲线。截图 `assets/idq-007/02-risk-dimensions.png`。

## 7. Acceptance / Rollback

- [ ] IR-01…10、真实API E2E和原PH-002共享预取回归通过。
- [ ] 无数据时没有假正常、无未经验证的买卖映射；解释与风险维度不冲突。
- [ ] 历史快照无重写，方法/时间/coverage在API、UI、export一致。
- [ ] 满足总计划全部质量门禁、截图、版本、changelog、案例和protected PR。
- [ ] 回滚禁用v2刷新而保留历史查看；不能恢复用假中性值兜底的新建议链路。

风险：新指标可能缺输入、旧UI依赖composite、指标相关性导致重复计分。宁可先发布
较少但可验证的维度，不为了“完整仪表盘”制造可疑精度。
