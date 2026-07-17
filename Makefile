# Financial Agent Development Makefile
# Following the coding guide requirements for fmt, test, lint commands

.PHONY: help dev build test test-e2e test-e2e-real test-e2e-uaw002 test-e2e-uaw003 lint fmt clean up down logs copilot-reverse

# Default target
help:
	@echo "Financial Agent Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  dev          Start development environment with hot reload"
	@echo "  up           Start all services with Docker Compose"
	@echo "  down         Stop all services"
	@echo "  logs         View logs from all services"
	@echo "  copilot-reverse  Start ../copilot-bridge on port 8765"
	@echo ""
	@echo "Code Quality:"
	@echo "  fmt          Format code (backend: black+ruff, frontend: prettier)"
	@echo "  lint         Lint code (backend: ruff+mypy, frontend: eslint)"
	@echo "  test         Run all tests"
	@echo "  test-e2e     Run deterministic Playwright browser tests"
	@echo "  test-e2e-real Run real-stack Playwright browser tests"
	@echo "  test-e2e-uaw002 Run Mongo-authority restart E2E"
	@echo "  test-e2e-uaw003 Run Deep Research context E2E"
	@echo ""
	@echo "Building:"
	@echo "  build        Build Docker images"
	@echo "  clean        Clean up Docker resources"

# Development
dev: up
	@echo "🚀 Development environment started!"
	@echo "Frontend: http://localhost:3000"
	@echo "Backend API: http://localhost:8000"
	@echo "Backend Docs: http://localhost:8000/docs"

up:
	docker-compose up -d
	@echo "⏳ Waiting for services to be ready..."
	@sleep 10
	@echo "✅ Services should be ready!"

down:
	docker-compose down

logs:
	docker-compose logs -f

copilot-reverse:
	cd ../copilot-bridge && dotnet run --project src/CopilotBridge.Cli -- serve --port 8765

# Code Quality - Backend
fmt-backend:
	@echo "🎨 Formatting backend code..."
	cd backend && python -m black src/
	cd backend && python -m ruff check --fix src/
	@echo "✅ Backend formatting complete"

lint-backend:
	@echo "🔍 Linting backend code..."
	cd backend && python -m ruff check src/
	cd backend && python -m mypy src/
	@echo "✅ Backend linting complete"

test-backend:
	@echo "🧪 Running backend tests..."
	docker-compose exec backend /home/app/.local/bin/pytest tests/ --cov=src --cov-report=term-missing
	@echo "✅ Backend tests complete"

# Code Quality - Frontend
fmt-frontend:
	@echo "🎨 Formatting frontend code..."
	cd frontend && npm run lint:fix
	@echo "✅ Frontend formatting complete"

lint-frontend:
	@echo "🔍 Linting frontend code..."
	cd frontend && npm run lint
	cd frontend && npm run type-check
	@echo "✅ Frontend linting complete"

test-frontend:
	@echo "🧪 Running frontend tests..."
	cd frontend && npm run test
	@echo "✅ Frontend tests complete"

# Combined commands
fmt: fmt-backend fmt-frontend
	@echo "🎨 All code formatted!"

lint: lint-backend lint-frontend
	@echo "🔍 All code linted!"

test: test-backend test-frontend
	@echo "🧪 All tests completed!"

test-e2e:
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; npm run test:e2e"

test-e2e-real:
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; npm run test:e2e:real"

test-e2e-uaw002:
	docker compose --profile e2e up -d --build llm-e2e backend-e2e frontend-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 1 FLUSHDB
	docker compose --profile e2e restart backend-e2e
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-002:seed"
	docker compose --profile e2e restart backend-e2e
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-002:resume"

test-e2e-uaw003:
	docker compose --profile e2e up -d --build llm-e2e backend-deep-e2e frontend-deep-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_deep_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 2 FLUSHDB
	docker compose --profile e2e restart backend-deep-e2e frontend-deep-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3002 e2e sh -c "until curl -fsS http://host.docker.internal:18083/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-003"

# Building
build:
	@echo "🏗️ Building Docker images..."
	docker-compose build
	@echo "✅ Build complete"

# Cleanup
clean:
	@echo "🧹 Cleaning up Docker resources..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup complete"

# Health checks
health:
	@echo "🏥 Checking service health..."
	@curl -s http://localhost:8000/api/health | python -m json.tool || echo "❌ Backend health check failed"
	@curl -s http://localhost:3000 > /dev/null && echo "✅ Frontend is responding" || echo "❌ Frontend health check failed"

# Database operations
db-shell:
	docker-compose exec mongodb mongosh financial_agent

redis-cli:
	docker-compose exec redis redis-cli

# Development utilities
install-backend:
	@echo "📦 Installing backend dependencies..."
	cd backend && pip install -e ".[dev]"

install-frontend:
	@echo "📦 Installing frontend dependencies..."
	cd frontend && npm install

install: install-backend install-frontend
	@echo "📦 All dependencies installed!"

# Git hooks setup
setup-hooks:
	@echo "🪝 Setting up git hooks..."
	cp scripts/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "✅ Git hooks installed"

backfill-translations:
	docker compose exec backend python -m scripts.backfill_translations --collection all
