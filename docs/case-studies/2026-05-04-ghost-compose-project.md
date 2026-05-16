---
title: Ghost Compose Project
status: shipped
version: n/a
last_updated: 2026-05-04
owner: maintainer
related_paths:
  - docker-compose.yml
---

# Ghost Compose Project：以为容器坏了，其实根本不是我们的容器

> **TL;DR (EN)**: `docker ps` showed our backend in a restart loop with
> `ModuleNotFoundError: No module named 'src'`. The whole afternoon was
> spent debugging the wrong containers — another `docker-compose` project
> on the same host had been auto-named identically and was running its
> own (broken) image. On Windows, Docker's bind mount also silently
> created an empty directory instead of refusing to start.
> **TL;DR (中文)**: `docker ps` 显示 backend 反复重启报
> `ModuleNotFoundError: No module named 'src'`，一整天都在 debug
> 错的容器——另一个 compose 项目在同一台机器上被自动命名成同名，跑的
> 是它自己的（坏的）镜像。Windows 下 Docker bind mount 还会**静默建
> 空目录**而不是直接拒绝启动。

> Date: 2026-05-04
> Component: Docker Compose / 本地开发环境
> Severity: 🟡 中等（阻塞了一天 E2E 验证，但代码没问题）

## 1. 背景 / Context

跨厂商 LLM 改造完成后要跑端到端验证。`docker ps` 显示：

```
financialagent-backend-1     Restarting (1) 39 seconds ago
financialagent-frontend-1    Restarting (254) 2 seconds ago
financialagent-portfolio-cron-1  Up 41 minutes (unhealthy)
financialagent-redis-1       Up 41 minutes
financialagent-mongodb-1     Up 41 minutes
```

backend 在重启循环。`docker logs financialagent-backend-1` 报：

```
ModuleNotFoundError: No module named 'src'
  File "uvicorn/importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
```

按 CLAUDE.md 要求要跑 `make test`，但 `test-backend` 通过 `docker compose exec backend pytest`，backend 起不来就跑不了测试。

## 2. 思考过程 / Reasoning

**第一反应：是不是我刚改的 `llm_factory.py` 导致 import 链断了？**
- 验证：`git stash` 把改动回退到 HEAD，`docker logs` 还是同样的错。✅ 排除我的改动。

**第二反应：是不是 cwd 不对？**
- Dockerfile 里 `WORKDIR /app`，CMD 是 `python -m uvicorn src.main:app`，需要 cwd=/app 且 `/app/src/main.py` 存在。
- `docker inspect financialagent-backend-1 --format '{{.Config.WorkingDir}}'` → `/app` ✅
- `docker inspect financialagent-backend-1 --format '{{.Config.Cmd}}'` → 命令也对 ✅

**第三反应：是不是 `/app/src` 没挂上？**
- 起一个 ad-hoc 容器复现：`docker run --rm -v D:/repo/FinancialAgent/backend:/app -w /app financialagent-backend python -c 'import src.main'` → **import 成功**！
- 关键证据：同样的镜像、同样的源码挂载，ad-hoc 能跑、正式容器跑不了。说明问题不在镜像、不在源码、不在 cwd。

**到这里我卡住了，因为镜像/cwd/源码三个最可能的因素都排除了。** 然后想到一个自己平时不太会查的方向 —— **挂载源到底是不是我以为的那个**：

```bash
docker inspect financialagent-backend-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

输出：
```
D:\repo\Nexis\FinancialAgent\backend -> /app
```

**`D:\repo\Nexis\FinancialAgent`！** 不是我们这个 `D:\repo\FinancialAgent`！

继续验证：
```bash
ls D:/repo/Nexis/FinancialAgent/backend/   # 空目录（只有 backend/ 这个名字，里面什么都没有）
docker inspect financialagent-backend-1 --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
# → D:\repo\Nexis\FinancialAgent
```

## 3. 根因 / Root cause

**Docker Compose 容器名按 `<project>_<service>_<index>` 命名，project 默认取 compose 文件所在的父目录名。** `D:\repo\Nexis\FinancialAgent` 和 `D:\repo\FinancialAgent` 都生成 project name `financialagent`，所以都生成同名容器 `financialagent-backend-1`。

时间线：
1. 早些时候在 `D:\repo\Nexis\FinancialAgent` 跑过 `docker compose up -d`
2. 后来把项目移走/重命名，留下空的 `Nexis/FinancialAgent/backend/` 目录
3. Docker daemon 仍然记得那套容器，bind mount 指向**已不存在内容的旧路径**。Windows bind mount 到不存在的源会**自动创建空目录**，所以 `/app` 是空的，自然 `import src` 失败
4. 我以为 `financialagent-backend-1` 是当前 repo 的容器，浪费时间在自己代码里找 bug

**为什么 ad-hoc 容器能跑：** ad-hoc 容器走的是当前 cwd 的 `-v` 参数（指向 `D:/repo/FinancialAgent/backend`），所以它挂的是真有源码的目录。

## 4. 解决方案 / Fix

```bash
# 1. 用 ghost project 的 working_dir 把 ghost 容器全停掉
docker compose --project-directory D:/repo/Nexis/FinancialAgent -p financialagent down

# 2. 从我们 repo 起 backend
cd D:/repo/FinancialAgent
docker compose up -d backend
```

backend 立即正常启动，`Application startup complete.`，零代码改动。

为什么不直接 `docker rm -f financialagent-backend-1`：会留下 network、volume 等悬挂资源；用 compose down 干净。

## 5. 教训 / Takeaways

1. **看到容器异常的第一反应应该是 "这个容器属于谁"，而不是 "我的代码哪里坏了"。** 优先用 `docker inspect <container> --format '{{.Config.Labels}}'` 确认 compose project 来源，再看 mount source。
2. **Windows bind mount 静默创建不存在的源目录是个隐藏陷阱。** Linux 下默认会拒绝挂载不存在的源（或挂出空目录但通常更明显）。Windows Docker Desktop 默默建空目录，导致 "为什么 `/app/src` 不见了" 这种问题极难定位。
3. **Compose project name 默认按 cwd 父目录名生成，不同路径下的同名仓库会互撞。** 多 worktree / 多副本场景下要么显式 `-p custom-name`，要么设 `COMPOSE_PROJECT_NAME` 环境变量。
4. **基础假设要常验证。** 我假设了 "正在跑的 `financialagent-backend-1` 就是我这个 repo 的"，结果错了一整天。`docker inspect` 里的 `Mounts` 和 `Labels` 字段是检查这种假设的最佳工具。
5. **ad-hoc 容器能跑 vs 守护容器跑不通的差异**——这种"同样的镜像表现不同"的现象，几乎一定指向**运行时的状态/挂载/环境变量差异**，不是代码差异。
