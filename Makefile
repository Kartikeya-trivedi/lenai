.PHONY: help setup up down build logs test lint migrate seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup: copy env, build, run migrations
	@test -f .env || cp .env.example .env
	@echo "✅ .env created — edit it with real values before starting"
	docker compose build
	docker compose up -d postgres redis minio qdrant
	@echo "⏳ Waiting for databases..."
	@sleep 5
	docker compose run --rm api alembic upgrade head
	@echo "✅ Setup complete. Run 'make up' to start all services."

up: ## Start all services
	docker compose up -d

up-gpu: ## Start all services with GPU support
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

down: ## Stop all services
	docker compose down

down-clean: ## Stop all services and remove volumes (DESTROYS DATA)
	docker compose down -v

build: ## Rebuild all containers
	docker compose build --no-cache

logs: ## Tail logs for all services
	docker compose logs -f

logs-api: ## Tail API logs only
	docker compose logs -f api worker

logs-models: ## Tail model container logs
	docker compose logs -f sd whisper kokoro vllm

test: ## Run test suite
	docker compose exec api pytest tests/ -v --cov=app --cov-report=term-missing

test-local: ## Run tests locally (requires virtualenv)
	cd api && pytest tests/ -v --cov=app

lint: ## Run linting
	cd api && ruff check app/ && ruff format --check app/

migrate: ## Run database migrations
	docker compose exec api alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new MSG="add users table")
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

seed: ## Seed development data
	docker compose exec api python scripts/seed_dev.py

loadtest: ## Run load tests with Locust
	docker compose exec api locust -f tests/locustfile.py --headless -u 20 -r 5 -t 60s --html=locust_report.html

e2e: ## Run E2E integration tests against live stack
	python scripts/test_e2e.py

health: ## Check health of all services
	@echo "API:     $$(curl -s http://localhost:8000/health | head -c 100)"
	@echo "SD:      $$(curl -s http://localhost:7860/sdapi/v1/options | head -c 50 || echo 'DOWN')"
	@echo "Whisper: $$(curl -s http://localhost:9090/health | head -c 50 || echo 'DOWN')"
	@echo "Kokoro:  $$(curl -s http://localhost:8880/v1/models | head -c 50 || echo 'DOWN')"
	@echo "Qdrant:  $$(curl -s http://localhost:6333/healthz | head -c 50 || echo 'DOWN')"
	@echo "vLLM:    $$(curl -s http://localhost:8001/health | head -c 50 || echo 'DOWN')"
	@echo "MinIO:   $$(curl -s http://localhost:9001 | head -c 50 || echo 'DOWN')"

clean: ## Remove generated files, caches, and temp data
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov coverage.xml locust_report*.html

