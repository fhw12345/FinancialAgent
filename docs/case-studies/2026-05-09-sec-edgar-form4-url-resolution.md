---
title: SEC EDGAR Form 4 URL Resolution
status: shipped
version: backend@0.27.x
last_updated: 2026-05-09
owner: maintainer
related_paths:
  - backend/src/agent/tools/sec_edgar/form4.py
---

# SEC EDGAR Form 4：从 atom feed 到 primary doc 的 URL 解析陷阱

> **TL;DR (EN)**: 18 unit tests with `httpx.MockTransport` were green, but
> the first integration test against the real SEC returned 404 on all 5
> filings — every filing-index URL was being transformed into a
> nonexistent primary-doc URL. The mocks accepted any string the code
> produced; the real EDGAR endpoint demanded a precise path shape.
> Lesson: when an external API has unforgiving URL conventions, the
> path-shape contract belongs in the unit suite, not just in slow
> integration runs.
> **TL;DR (中文)**: 18 个 `httpx.MockTransport` 单测全绿，第一个集成测试
> 打真实 SEC 时 5 个 filing 全部 404——`...-index.htm` → primary doc XML
> 的 URL 转换写错了。Mock 接受任何字符串，真 EDGAR 要精确路径。教训：
> 外部 API 的 URL 约定不容错时，路径形状本身应该作为契约测试在单测里
> 就锁死。

> Date: 2026-05-09
> Component: backend/src/agent/tools/sec_edgar/form4.py
> Severity: 🟠 中高（W3.9 单元测试全绿，但生产路径会 5 个 filing 全部 404，PRD AC#3 在生产环境零通过）

## 1. 背景 / Context

W3.9 实现 `Form4Client.fetch_recent_transactions(symbol, count)` —— 端到端
拉 SEC EDGAR Form 4 内幕交易记录。整条链路：

1. `lookup_cik(symbol)` → 查 ticker→CIK 映射（10 位零填充）
2. `fetch_form4_atom(symbol)` → 拉 atom feed
3. `parse_atom_filing_index_urls(xml)` → 提取每个 entry 的 filing-index URL
4. `_index_to_form4_xml_url(url)` → 把 `...-index.htm` 转成 primary doc XML URL
5. `parse_form4_detail(xml)` → 把 ownership-document XML 解析成
   `Form4Transaction` 列表

W3.9 全套 18 个单元测试用 `httpx.MockTransport` 模拟 SEC，35/35 全绿，
PR 合并。W3.13 加了 `@pytest.mark.integration` 真打 SEC 的集成测试。

第一次跑 `test_fetch_recent_transactions_nvda_populates_plan_type`
（PRD AC#3：≥3 of N parsed transactions 必须有 `plan_type` 填充）：

```
assert 0 >= 3
+  where 0 = len([])
```

5 个 filing 全部 404。

## 2. 思考过程 / Reasoning

### 第一反应（错的）：rate limit / User-Agent 出问题了

PRD D4 明确要求 `User-Agent: ffffhhhww@qq.com`，AC#5 要求 < 10 req/s。
SEC 对 User-Agent 缺失会返回 soft warning 而不是真 block，但还是先排查
这层 —— 单独跑 `test_lookup_cik_nvda_resolves` 通过，CIK = `0001045810`
（NVDA 的 pinned CIK），ticker 映射拉通了。说明 User-Agent 和基础连通性
都 OK。

### 第二反应：看 404 URL 长什么样

日志里五条都是同一形状：

```
404: https://www.sec.gov/Archives/edgar/data/1045810/000119903926000003/0001199039-26-000003.xml
```

URL 是 `_index_to_form4_xml_url` 拼出来的：

```python
def _index_to_form4_xml_url(index_url: str) -> str | None:
    for suffix in ("-index.htm", "-index.html"):
        if index_url.endswith(suffix):
            return index_url[: -len(suffix)] + ".xml"
    return None
```

把 `0001199039-26-000003-index.htm` 变成 `0001199039-26-000003.xml`。
W3.9 注释里写得很自信：

> EDGAR's URL convention is to take the index URL, strip the trailing
> `-index.htm[l]?` and append a hint that asks for the primary document.
> ...empirically that yields the primary doc for >90% of Form 4s.

### 第三反应：手 curl 一遍验证

```bash
curl -s "https://www.sec.gov/Archives/edgar/data/1045810/000119903926000003/" \
  | grep -oE 'href="[^"]+\.xml"'
# href="/Archives/edgar/data/1045810/000119903926000003/wk-form4_1774386816.xml"
```

primary doc 实际叫 `wk-form4_1774386816.xml`。完全不是 `<accession>.xml`。

抽样 5 个 NVDA 最近 filing：每一个的 primary doc 文件名都不一样：
- `wk-form4_1774386816.xml`
- `xslF345X05/wk-form4_xxxxxxxx.xml`
- `primary_doc.xml`
- `edgar.xml`
- `<reporter>-form4-<id>.xml`

W3.9 注释的 "convention" 是**捏造的**。EDGAR 对 Form 4 没有 primary doc
文件名约定 —— 不同 filing agent / 不同年代写出的 XML 文件名各不相同。

### 第四反应：那 W3.9 的 35/35 单元测试为什么全绿？

因为 mock handler 自己定义了"约定"：

```python
if url.endswith("0000320193-26-000123.xml"):
    return httpx.Response(200, text=detail_a, ...)
```

mock 的 URL pattern 是测试作者**自己规定的**。`MockTransport` 接受的就是
后缀 swap 的 URL —— 测试在自我证明而不是证伪。

这是 mock 测试最经典的失败模式：**fixture 定义了 SUT 的接口，而不是验证
SUT 真的能和外界 contract 对得上**。

### 第五反应：正确的 primary doc 怎么找？

curl 文件夹本身：

```bash
curl -s "https://www.sec.gov/Archives/edgar/data/1045810/000119903926000003/index.json"
# {
#   "directory": {
#     "item": [
#       {"name": "0001199039-26-000003-index-headers.html"},
#       {"name": "0001199039-26-000003-index.html"},
#       {"name": "0001199039-26-000003.txt"},
#       {"name": "wk-form4_1774386816.xml"}
#     ]
#   }
# }
```

SEC 给每个 filing 文件夹自动生成 `index.json`，结构化列出所有文件。
**这才是该用的 contract** —— 不要猜文件名，去问目录。

## 3. 根因 / Root Cause

W3.9 设计阶段我（main agent）做了两个相互掩盖的错误判断：

1. **基于"看一眼"得出 URL 约定**：开发期我只看了一两个 Apple 的 filing，
   恰好是用 `<accession>.xml` 写的（很少见的子集），就推广成"convention"。
   没有 sample 不同年代 / 不同 filer 的 filing。
2. **mock 测试用 SUT 自己生成的 URL 做断言**：handler 接受 SUT 拼出来的
   URL 是同语反复，根本没有外部 contract 检查。集成测试的真正价值就在这种
   场景才显形 —— 单元测试在闭环里完美，生产环境零成功率。

第二条是这次的核心教训。**用真实数据 record/replay** 也可以，但成本更高；
最低成本的纠偏是：**至少加一个 staging fixture（保存自真实 SEC 响应的
sample），让 mock 跑同样的 fixture，然后再跑生产路径覆盖一次**。

## 4. 修复 / Fix

加一个新的 async resolver，把"猜文件名"换成"问目录"：

```python
async def _resolve_form4_doc_url(client: Form4Client, index_url: str) -> str | None:
    folder = _filing_folder_from_index_url(index_url)
    if folder is None:
        return _index_to_form4_xml_url(index_url)  # 老后缀 swap 兜底
    manifest_url = folder + "index.json"
    try:
        resp = await client._request(manifest_url)
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return _index_to_form4_xml_url(index_url)
    items = (data.get("directory") or {}).get("item") or []
    for entry in items:
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str) and name.lower().endswith(".xml"):
            return folder + name
    return _index_to_form4_xml_url(index_url)
```

设计要点：

- **不删原 `_index_to_form4_xml_url`**：保留为兜底分支。manifest 拉失败 /
  没有 XML 时用，这样 W3.9 现有 35 个 mock 测试不需要改 —— 它们的 mock
  handler 对 `index.json` 返回 404，自动落回旧路径，行为完全保持。
- **manifest 失败不抛**：individual filing 拉不到 manifest 是常见情况
  （某些古老 filing 没有 index.json），不应该让一个 filing 的解析失败
  把整批拖死。
- **rate limit 仍然走 `_request`**：manifest 多了一次 HTTP 请求，但每次
  都过 token bucket，AC#5 < 10/s 不动摇（实测 50 sequential = 0.69 req/s）。

集成测试新增 9 个，单元测试新增 3 个（resolver 的 happy path / manifest
失败兜底 / 没有 XML 文件兜底），W3.9 老的 18 个测试零修改全过。

## 5. 验证 / Verification

```bash
docker compose exec backend pytest tests/test_form4_parser.py
# 21 passed (18 W3.9 + 3 resolver)

docker compose exec backend pytest tests/test_form4_real.py -m integration
# 9 passed in 72.92s
# - PRD AC#3: NVDA fetch_recent_transactions 返回 ≥3 tx，全部 plan_type 填充
# - PRD AC#5: 50 sequential calls 在 < 10 req/s 范围内
```

## 6. 收获 / Takeaways

1. **mock 测试容易自证而不证伪**。当 SUT 生成 URL 然后 mock handler 用
   "endswith(SUT 生成的相同后缀)" 来匹配 —— 测试在验证字符串相等，不在
   验证外部协议。修法：mock fixture 必须用真实抓的样本，而不是从代码
   推回的样本。
2. **integration test 是 contract 的最低成本验证**。不必 record/replay
   全部，关键路径打一次真实 endpoint 就能暴露 mock 的盲区。这次 W3.9
   合并到 W3.13 跑真实 SEC 之间隔了 4 个 commit —— 越早跑集成测试，
   反馈成本越低。
3. **不要在注释里写"convention"**。如果协议没有正式文档，写"我观察到这样"
   就好；把"observation"包装成"convention"会让后续 reader 跳过验证。
   这次的"yields >90%"是完全错的（实际 0%），但读到的人不会怀疑。
4. **保留旧路径作为 fallback 比直接替换更安全**。新 resolver 加在前面，
   老 swap 留在后面 —— 老测试零修改，老兜底也还在。如果 SEC 哪天禁掉
   `index.json`（不会，但万一），生产至少不会一夜清零。
5. **fixture 要能被覆盖**：W3.9 的 fixture 应该用 `wk-form4_<id>.xml`
   而不是 `<accession>.xml`，把"primary doc 文件名变化"明确写进 setup。
   集成测试发现这个问题之后，W3.13 提交里把 mock fixture 也改了一份
   就更稳 —— 不过这次没改，因为旧 fixture 现在变成"测兜底分支"反而
   有正面含义（manifest 找不到时还能 swap 出 URL，虽然现实里 swap 不
   命中真实文件，但 mock 验证这条分支的 control flow）。
