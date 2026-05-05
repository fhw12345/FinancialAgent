# "代码改了 / 容器看得见 / 浏览器没生效"：Vite + Docker on Windows 的 HMR 静默失效

> Date: 2026-05-06
> Component: Vite dev server / Docker bind mount / inotify
> Severity: 🟠 高（用户反馈"还是 raw md"时我已经 commit 过了；改对了但 prod 端看不到）

## 1. 背景 / Context

刚把 DecisionTracker 的 Full Research modal 改成 ReactMarkdown 渲染（v0.16.3）。改完代码、ESLint 跑过、Vite log 没报错——按惯例就 ship。

用户：**"现在页面上 full research 还是 raw md"**

第一反应是不是哪里没保存到、或者编辑器同步出错。

## 2. 思考过程 / Reasoning

### 假设 1：文件没保存

`grep -n "ResearchBody" DecisionTracker.tsx` → 第 16 行 import、第 365 行注释、368 行函数定义、848 行 modal 调用。**文件本身写得好好的。**

### 假设 2：容器里的文件没同步

Docker bind mount 用的是 `volumes: ./frontend:/app`，理论上主机改动应该即时同步。但 Windows + Docker 下 bind mount 是经典坑区——验证一下：

```bash
docker compose exec -T frontend sh -c 'grep -c "ResearchBody" /app/src/components/portfolio/DecisionTracker.tsx'
# 输出: 2
```

容器里**能看到 ResearchBody**——文件内容确实同步过去了。所以不是 bind mount 没传内容。

### 假设 3：浏览器缓存

强刷？但用户说他打开就是 raw md，且改动前后 modal 行为完全没变（一直是 raw md），不像是从中间某个旧 bundle 卡住。

### 真相：Vite 完全没察觉文件变了

看 frontend logs：

```
frontend-1  | > financial-agent-frontend@0.16.0 dev
frontend-1  | > vite
frontend-1  |   VITE v5.4.20  ready in 303 ms
frontend-1  |   ➜  Local:   http://localhost:3000/
```

容器**启动于约 1 小时前**（package.json 那时还是 0.16.0，现在是 0.16.3）——也就是说我做了三次 frontend 改动 + 三次版本 bump，**Vite log 里完全没出现任何文件变更触发的 HMR 重编译**。

正常 HMR 触发时会看到：
```
[vite] hmr update /src/components/portfolio/DecisionTracker.tsx
```

我的 logs 里**一行都没有**。

文件内容到了容器里、Vite 进程在跑、浏览器请求能进来——**但 Vite 的 file watcher 对文件改动一无所知**。bundle 还是 1 小时前那个，浏览器拿到的当然是旧版。

## 3. 根因 / Root cause

**Docker on Windows 的 bind mount 不传 inotify 事件。**

技术细节：
1. Linux 容器里的 Vite/chokidar 用 inotify 监听文件变化
2. inotify 只在文件系统事件**在同一个内核**里发生时才触发
3. Windows 主机的文件系统改动是 NTFS 层面的，要透过 9P/SMB（取决于 Docker Desktop 后端是 WSL2 还是 Hyper-V）传到 Linux 容器
4. 协议层把**文件内容**同步过去了（VFS 看得到新内容），但**inotify 事件**没被代理过来

结果：

| 检测方法 | 容器内结果 |
|---------|----------|
| `cat` / `grep` 文件内容 | ✅ 看到新内容 |
| `stat` mtime | ✅ 看到新 mtime |
| `inotifywait` 监听 | ❌ 完全没事件 |

Vite/chokidar 默认靠 inotify。事件不来 = HMR 不触发 = bundle 不重建。**完全静默失败**——没有任何错误日志，进程一切正常，只是 watcher 在睡觉。

### 为什么这么久才发现

我之前每次改完都跑 `docker compose restart frontend`——以为只是版本号 bump 后的好习惯。其实**那次重启等于在帮 Vite 做了它自己应该做的事**（重新读文件、重新 bundle）。所以问题被无意中绕过了。这次因为我连续做了三波改动（v0.16.1 / 0.16.2 / 0.16.3），自以为前两次改动让 Vite "热加载"了，实际上从 v0.16.0 起 Vite 就**根本没动过 bundle**——前两次改动只是巧合地不影响显示，第三次才暴露。

## 4. 解决方案 / Fix

`vite.config.ts` 的 `server.watch` 加 polling：

```typescript
server: {
  host: "0.0.0.0",
  port: 3000,
  strictPort: true,
  // Docker on Windows: bind-mounted file changes don't fire inotify events,
  // so Vite's default fs watcher misses HMR triggers and you have to
  // restart the container after every edit. Polling at 1s catches changes
  // without inotify; cost is a few % CPU for the watcher process.
  watch: {
    usePolling: true,
    interval: 1000,
  },
},
```

polling 的 watcher **不依赖事件**——每 1 秒主动 stat 所有 watch 的文件、对比 mtime。事件层是脏的没关系，文件系统层是干净的。

代价：watcher 进程多吃 2-3% CPU（笔记本可能更明显，省电模式下要注意）。

vite.config.ts 自己的改动需要 frontend 容器重启一次才生效（HMR 都还没开，配置改动当然不会被 HMR 检测到）。**之后**所有前端代码改动 HMR 都会自动触发，不再需要重启。

## 5. 教训 / Takeaways

1. **"容器看得见文件 ≠ Vite 看得见文件"**。bind mount 同步的是 VFS 层（内容、mtime），inotify 是事件层。两者独立。当 dev server 看起来在跑但浏览器拿不到新代码时，不要先怀疑代码——先 `docker logs` 看 watcher 有没有触发事件。判断方法：改一个文件后看 Vite log 里有没有 `[vite] hmr update`，没有就是 watcher 失效。

2. **静默失败比报错难抓**。如果 Vite 直接报"file watcher 失败"我会立刻发现。但它就是**安静地不工作**——所有日志正常、所有 lint 通过、所有 tool call 成功，只有"代码改了但浏览器看不到"这个终端症状。**这种"全部上游正常但下游观测不到"的失败模式是 Docker 多层抽象的特产**——每一层单独都"成功"了，组合起来失败。

3. **跨 OS dev 环境的 HMR 配置应该写在 vite.config.ts 不是文档里**。"Windows 用户记得开 polling" 写在 README 里没人会看；写在 `vite.config.ts` 里 polling 永远开（Linux/Mac 也兼容，只是浪费一点 CPU），新人 clone 项目立即可用。**配置即文档**——能用代码表达的约定不要靠文档。

4. **`docker compose restart` 不是 Vite 工作流的一部分**。如果你正常的"改代码 → 看效果"循环里需要手动重启 dev container，那 dev server 的核心承诺（HMR）已经失效。要么修配置（polling），要么承认这事（README 写明），但不要假装它在工作。

5. **被自己的好习惯掩盖的 bug 最难发现**。我每次 bump 版本号后习惯性 `docker compose restart frontend`——这个习惯掩盖了 HMR 失效整整 N 周（甚至更久）。**好习惯能掩盖问题，跟坏习惯一样需要被审视**。"为什么我每次都要重启？这正常吗？" 是值得问的问题。面试可以说：debug 时不仅看"我现在做了什么没用"，还要看"我历史上一直在做什么——那是不是在掩盖问题"。

6. **改完代码 ship 之前先在浏览器看一眼**。这次我以为 Vite log 没报错就够了——typecheck 过、lint 过、容器健康。但**没有任何这些检查能验证浏览器拿到的 bundle 跟我想要的 bundle 一致**。前端改动的真正验证只有一个：**真的打开浏览器看一眼**。这是个最初级也最容易跳过的纪律——CLAUDE.md 里就明确写了"For UI or frontend changes, start the dev server and use the feature in a browser before reporting the task as complete"，本次没做到，被用户反馈打脸。

7. **同一个错过的纪律可能产生连锁后果**。如果第一次 frontend 改动（v0.16.1）我就在浏览器测过，会立刻发现 HMR 失效，会立刻修 polling，那后续两个改动（0.16.2 / 0.16.3）就直接有 HMR 兜底——而不是等到 v0.16.3 用户反馈才暴露。**纪律的复利效应是它最容易被低估的价值**。

## 相关

- [2026-05-04-ghost-compose-project.md](2026-05-04-ghost-compose-project.md) — 同一个"Docker 多层抽象 + Windows 平台特殊行为"家族
- [2026-05-05-translation-pipeline-multilayer.md](2026-05-05-translation-pipeline-multilayer.md) — 同一轮 session 用户反馈连环引发的多层根因，本篇是其中第 4 次反馈"还是 raw md"暴露的隐藏层
