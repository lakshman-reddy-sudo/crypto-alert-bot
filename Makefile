# ─────────────────────────────────────────────────────────────────────────────
# Makefile — Developer convenience targets for crypto-alert-bot
#
# Usage:
#   make install       Install all dependencies (creates .venv)
#   make run           Start the bot locally
#   make test          Run the full test suite
#   make test-cov      Run tests with coverage report
#   make migrate       Apply pending DB migrations
#   make migrate-status Show migration status
#   make lint          Run ruff linter
#   make typecheck     Run mypy type checker
#   make docker-build  Build the Docker image
#   make docker-up     Start all services with docker-compose
#   make docker-down   Stop all docker-compose services
#   make docker-logs   Tail the bot container logs
#   make clean         Remove cache files and .venv
# ─────────────────────────────────────────────────────────────────────────────

PYTHON     := python3
VENV       := .venv
PIP        := $(VENV)/bin/pip
PYTEST     := $(VENV)/bin/pytest
PYTHON_V   := $(VENV)/bin/python

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ─────────────────────────────────────────────────────────────────────
.PHONY: install
install: ## Create .venv and install all dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "  Done. Activate with:  source $(VENV)/bin/activate"

# ── Run ───────────────────────────────────────────────────────────────────────
.PHONY: run
run: ## Start the bot (requires .env to be configured)
	@test -f .env || (echo "ERROR: .env not found. Copy .env.example and fill in the values." && exit 1)
	@export $$(cat .env | grep -v '^#' | xargs) && $(PYTHON_V) bot.py

# ── Testing ───────────────────────────────────────────────────────────────────
.PHONY: test
test: ## Run the full test suite
	$(PYTEST) tests/ -v

.PHONY: test-cov
test-cov: ## Run tests with terminal coverage report
	$(PYTEST) tests/ -v \
		--cov=. \
		--cov-omit="tests/*,migrations/*,.venv/*" \
		--cov-report=term-missing

.PHONY: test-fast
test-fast: ## Run tests, stop on first failure
	$(PYTEST) tests/ -v -x

# ── Migrations ────────────────────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Apply all pending database migrations
	@test -f .env || (echo "ERROR: .env not found." && exit 1)
	@export $$(cat .env | grep -v '^#' | xargs) && $(PYTHON_V) migrations/migrate.py

.PHONY: migrate-status
migrate-status: ## Show which migrations have been applied
	@test -f .env || (echo "ERROR: .env not found." && exit 1)
	@export $$(cat .env | grep -v '^#' | xargs) && $(PYTHON_V) migrations/migrate.py --status

.PHONY: migrate-dry
migrate-dry: ## Preview pending migrations without applying
	@test -f .env || (echo "ERROR: .env not found." && exit 1)
	@export $$(cat .env | grep -v '^#' | xargs) && $(PYTHON_V) migrations/migrate.py --dry-run

# ── Code Quality ──────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Run ruff linter (pip install ruff)
	@$(VENV)/bin/ruff check . --exclude .venv

.PHONY: lint-fix
lint-fix: ## Auto-fix ruff lint issues
	@$(VENV)/bin/ruff check . --fix --exclude .venv

.PHONY: typecheck
typecheck: ## Run mypy type checker (pip install mypy)
	@$(VENV)/bin/mypy bot.py alerts.py data.py price_stream.py config.py healthcheck.py \
		--ignore-missing-imports \
		--no-strict-optional

.PHONY: fmt
fmt: ## Format code with ruff formatter
	@$(VENV)/bin/ruff format . --exclude .venv

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker-build
docker-build: ## Build the Docker image
	docker build -t crypto-alert-bot:latest --target runtime .

.PHONY: docker-up
docker-up: ## Start the bot (and monitoring if --profile monitoring passed)
	docker compose up -d
	@echo ""
	@echo "  Bot running. Tail logs with:  make docker-logs"
	@echo "  Health check:                 curl http://localhost:8080/ready"

.PHONY: docker-up-monitoring
docker-up-monitoring: ## Start with Prometheus + Grafana monitoring stack
	docker compose --profile monitoring up -d

.PHONY: docker-down
docker-down: ## Stop all docker-compose services
	docker compose down

.PHONY: docker-logs
docker-logs: ## Tail the bot container logs (Ctrl-C to stop)
	docker compose logs -f bot

.PHONY: docker-shell
docker-shell: ## Open a shell inside the running bot container
	docker compose exec bot /bin/sh

.PHONY: docker-restart
docker-restart: ## Restart only the bot container
	docker compose restart bot

# ── Health check shortcut ─────────────────────────────────────────────────────
.PHONY: health
health: ## Check bot health endpoints (requires running bot)
	@echo "=== /health ===" && curl -s http://localhost:8080/health | python3 -m json.tool
	@echo ""
	@echo "=== /ready ===" && curl -s http://localhost:8080/ready | python3 -m json.tool
	@echo ""
	@echo "=== /metrics ===" && curl -s http://localhost:8080/metrics

# ── Clean ─────────────────────────────────────────────────────────────────────
.PHONY: clean
clean: ## Remove __pycache__, .pytest_cache, and .venv
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -not -path "./.venv/*" -delete 2>/dev/null || true
	rm -rf .venv
	@echo "Cleaned."
