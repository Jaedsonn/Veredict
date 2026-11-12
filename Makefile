.DEFAULT_GOAL := help
.PHONY: help install up down logs db dev-web dev-auth migrate migration test db-test-contract lint format check

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:
	@test -f .env || cp .env.example .env
	npm install
	uv sync

up:
	docker compose up -d --build --wait

down:
	docker compose down

logs:
	docker compose logs -f

db:
	docker compose up -d --wait mysql

dev-web:
	npm run dev:web

# No futuro a gente vai fazer um geral para todos os serviços
# Mas por enquanto bora deixar somente para cada serviço específico
dev-auth:
	uv run uvicorn auth_service.main:create_app --factory --reload --port 8001

migrate:
	uv run alembic -c services/auth/alembic.ini upgrade head

migration:
	uv run alembic -c services/auth/alembic.ini revision --autogenerate -m "$(m)"

test:
	uv run pytest

# Contrato do banco (privilégios, UTC, tipos) num MySQL descartável com docker/mysql/init
DB_CONTRACT := veriditi-db-contract
DB_CONTRACT_ENV := CONTRACT_DB_PORT=3317 DB_MIGRATOR_PASSWORD=m AUTH_DB_PASSWORD=a \
	NOTIFICATION_DB_PASSWORD=n LOGS_DB_PASSWORD=l

db-test-contract:
	@docker rm -f $(DB_CONTRACT) >/dev/null 2>&1 || true
	docker run --rm -d --name $(DB_CONTRACT) -p 3317:3306 \
		-e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=veriditi $(addprefix -e ,$(DB_CONTRACT_ENV)) \
		-v "$(CURDIR)/docker/mysql/init:/docker-entrypoint-initdb.d:ro" \
		mysql:8.4 --default-time-zone=+00:00 >/dev/null
	@# TCP só responde depois do initdb (o servidor temporário roda sem rede)
	@for i in $$(seq 1 60); do \
		docker exec $(DB_CONTRACT) mysql -uroot -proot -h127.0.0.1 -e 'SELECT 1' >/dev/null 2>&1 && break; \
		sleep 2; \
	done
	@$(DB_CONTRACT_ENV) uv run pytest -m mysql libs/python/common/tests/mysql; \
		status=$$?; docker rm -f $(DB_CONTRACT) >/dev/null; exit $$status

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy services/*/src libs/python/*/src
	npm run lint:web
	npm run typecheck:web

format:
	uv run ruff check --fix .
	uv run ruff format .

check: lint test
