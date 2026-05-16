# Financial Agent - 个人本地工具

> This is a personal single-user local fork. Cloud deployment, multi-user auth,
> and credit billing have been removed. Run via `docker compose up`, hit
> `localhost:3000`.

## Tech Stack

| Layer    | Technology                                       |
| -------- | ------------------------------------------------ |
| Backend  | Python 3.12 + FastAPI + MongoDB + Redis          |
| Frontend | React 18 + TypeScript 5 + Vite + TailwindCSS     |
| AI / LLM | LangChain + LangGraph + Alibaba DashScope (Qwen) |
| Runtime  | Docker Compose (local only)                      |

## Local Development

```bash
make dev               # docker compose up (backend, frontend, mongo, redis)
make test              # run all tests
make fmt && make lint  # format + lint
docker compose logs -f backend
curl http://localhost:8000/api/health
```

Frontend commands run inside the container:
`docker compose exec frontend npm <cmd>`

After changing any `.env*` file:
`docker compose up -d --force-recreate <service>` — `restart` does NOT reload env vars.

## Code Standards

- Python: Black + Ruff + mypy
- TypeScript: Prettier + ESLint (security + perf plugins)
- File length: max 500 lines per source file
- Pre-commit hook enforces version bump on every commit
- See `docs/development/coding-standards.md`

## Security Rules

NEVER commit secrets (API keys, tokens, passwords, connection strings).

- Use `.env` (gitignored) for local secrets
- Placeholders in committed files: `YOUR_KEY_HERE`, `<REDACTED>`
- Run `git diff --staged` before committing and scan for keys

## Before Committing

- [ ] Test locally — verify the change works in the browser / terminal
- [ ] `make fmt && make test && make lint`
- [ ] Bump version: `./scripts/bump-version.sh [backend|frontend] [patch|minor|major]`
- [ ] Update `docs/project/versions/[component]/CHANGELOG.md`
- [ ] No secrets staged

## Development Principles

- Find the root cause; don't patch symptoms
- Start with the simplest fix that works
- Avoid duplicating logic across files
- Compare environments when something works locally but not elsewhere

## Documentation Rules

- 所有 `docs/features/*.md` 必须使用统一 YAML frontmatter（`status` / `version` / `last_updated` / `owner` / `related_paths`）
- `status` 字段枚举：`draft` | `planning` | `in-progress` | `shipped` | `superseded`
- 日期一律 ISO 格式 `YYYY-MM-DD`
- 内部链接全部相对路径；新增 doc 时必须更新 `docs/README.md`
- 添加 / 修改 feature 时同步 `docs/features/<name>.md` 的 `last_updated` 与 `version`
- 修 bug / 踩坑后写一篇 `docs/case-studies/YYYY-MM-DD-<slug>.md`
- 完整规则见 [`docs/development/documentation.md`](docs/development/documentation.md)
