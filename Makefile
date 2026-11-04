.DEFAULT_GOAL := help
.PHONY: help install up down logs db dev-web dev-users migrate migration test lint format check

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
dev-users:
	uv run uvicorn users_service.main:create_app --factory --reload --port 8001

migrate:
	uv run alembic -c services/users/alembic.ini upgrade head

migration:
	uv run alembic -c services/users/alembic.ini revision --autogenerate -m "$(m)"

test:
	uv run pytest

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
