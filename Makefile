.DEFAULT_GOAL := help
.PHONY: help install up down reset logs db dev dev-web migrate migration test lint format check \
	db-test db-test-contract db-test-migrations _migrations-check

# Variáveis da linha de comando vão para o ambiente das receitas, e exportar expande o valor:
# um m='$(shell ...)' executaria. As receitas leem m e s por $(value), nunca do ambiente
unexport m s

SERVICES := gateway auth notification monitoring
# Serviço com banco é o que tem alembic.ini
DB_SERVICES := $(patsubst services/%/alembic.ini,%,$(wildcard services/*/alembic.ini))

# Portas do `make dev`; no compose todos escutam na 8000
PORT_gateway := 8080
PORT_auth := 8001
PORT_notification := 8002
PORT_monitoring := 8003

# Usuário de runtime, variável do .env com a senha dele e banco (padrão veriditi)
DB_USER_auth := auth_svc
DB_USER_notification := notification_svc
DB_USER_monitoring := veriditi_logs_writer
DB_PASS_auth := AUTH_DB_PASSWORD
DB_PASS_notification := NOTIFICATION_DB_PASSWORD
DB_PASS_monitoring := LOGS_DB_PASSWORD
DB_NAME_monitoring := veriditi_logs

empty :=
space := $(empty) $(empty)
need_s = $(if $(filter $(s),$(SERVICES)),,$(error use s=<$(subst $(space),|,$(SERVICES))>))
need_db_s = $(if $(filter $(s),$(DB_SERVICES)),,$(error use s=<$(subst $(space),|,$(DB_SERVICES))>))

# Lê uma chave sem executar o .env: o ambiente vence, senão a última linha KEY= sem aspas
env_get = env_get() { printenv "$$1" || { [ -f .env ] && grep -E "^$$1=" .env | tail -n 1 | \
	cut -d= -f2- | sed -e "s/^\"\(.*\)\"$$/\1/" -e "s/^'\(.*\)'$$/\1/"; }; };

# O resto do .env (DB_HOST, DB_PORT, DB_MIGRATOR_PASSWORD...) o pydantic lê sozinho
svc_env = $(if $(DB_USER_$(s)),$(env_get) export DB_NAME=$(or $(DB_NAME_$(s)),veriditi) \
	DB_USER=$(DB_USER_$(s)) DB_MIGRATOR_USER=migrator \
	DB_PASSWORD="$$(env_get $(DB_PASS_$(s)))";)

help:
	@grep -E '^[a-zA-Z-][a-zA-Z_-]*:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependências e cria o .env a partir do .env.example
	@test -f .env || cp .env.example .env
	npm install
	uv sync

up: ## Sobe o stack completo e espera todos ficarem saudáveis
	docker compose up -d --build --wait

# Parar e ler logs não depende das senhas: o .env.example só preenche o que falta no .env,
# que vem por último e vence (inclusive COMPOSE_PROJECT_NAME)
compose_any = docker compose --env-file .env.example $(if $(wildcard .env),--env-file .env)

down: ## Para o stack, inclusive containers de serviços que saíram do compose (mantém o volume)
	$(compose_any) down --remove-orphans

reset: ## Apaga o volume do MySQL: reaplica docker/mysql/init e as migrations
	$(compose_any) down -v --remove-orphans

logs: ## Acompanha os logs do stack
	$(compose_any) logs -f

db: ## Sobe só o MySQL no Docker
	docker compose up -d --wait mysql

dev: ## Serviço com hot reload (s=gateway|auth|notification|monitoring)
	$(need_s)@$(svc_env) uv run uvicorn $(s)_service.main:create_app --factory --reload \
		--port $(PORT_$(s)) --reload-dir services/$(s)/src --reload-dir libs/python/common/src

dev-web: ## Web com hot reload
	npm run dev:web

migrate: ## Aplica as migrations (s=<serviço> ou todos os serviços com banco)
ifdef s
	$(need_db_s)@$(svc_env) uv run alembic -c services/$(s)/alembic.ini upgrade head
else
	@for svc in $(DB_SERVICES); do $(MAKE) --no-print-directory migrate s=$$svc || exit 1; done
endif

# Id sequencial de 4 dígitos (§11) a partir do nome YYYYMMDD_<rev>_<slug>.py; m vai entre
# aspas simples com $(value) para nem o make nem o sh interpretarem a mensagem
migration: ## Nova revisão autogerada com id sequencial (s=<serviço> m="mensagem")
	$(need_db_s)$(if $(value m),,$(error use m="mensagem"))@$(svc_env) \
	rev=$$(ls services/$(s)/migrations/versions | \
		sed -n 's/^[0-9]\{8\}_\([0-9]\{4\}\)_.*\.py$$/\1/p' | sort -n | tail -n 1); \
	rev=$$(printf '%04d' "$$(expr "$${rev:-0}" + 1)"); \
	uv run alembic -c services/$(s)/alembic.ini revision --autogenerate --rev-id "$$rev" \
		-m '$(subst ','\'',$(value m))'

test: ## Testes Python sem MySQL (s=<serviço> opcional)
	uv run pytest $(if $(s),services/$(s))

# MySQL descartável na 3317 com docker/mysql/init (mesmo comando local e no CI, ADR-023)
DB_TEST := veriditi-db-test
DB_CONTRACT_ENV := CONTRACT_DB_PORT=3317 DB_MIGRATOR_PASSWORD=m AUTH_DB_PASSWORD=a \
	NOTIFICATION_DB_PASSWORD=n LOGS_DB_PASSWORD=l

define db_test_up
	@docker rm -f $(DB_TEST) >/dev/null 2>&1 || true
	docker run --rm -d --name $(DB_TEST) -p 127.0.0.1:3317:3306 \
		-e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=veriditi $(addprefix -e ,$(DB_CONTRACT_ENV)) \
		-v "$(CURDIR)/docker/mysql/init:/docker-entrypoint-initdb.d:ro" \
		mysql:8.4 --default-time-zone=+00:00 >/dev/null
	@# TCP só responde depois do initdb (o servidor temporário roda sem rede)
	@for i in $$(seq 1 60); do \
		docker exec $(DB_TEST) mysql -uroot -proot -h127.0.0.1 -e 'SELECT 1' >/dev/null 2>&1 \
			&& exit 0; \
		sleep 2; \
	done; echo "MySQL de teste não respondeu"; docker rm -f $(DB_TEST) >/dev/null; exit 1
endef

db_test_down = docker rm -f $(DB_TEST) >/dev/null

db-test: db-test-contract db-test-migrations ## Tudo que precisa de MySQL real (roda no CI)

db-test-contract: ## Contrato do banco e testes marcados como mysql
	$(db_test_up)
	@$(DB_CONTRACT_ENV) uv run pytest -m mysql; status=$$?; $(db_test_down); exit $$status

db-test-migrations: ## heads, upgrade, check, downgrade e upgrade de cada serviço com banco
	$(db_test_up)
	@status=0; for svc in $(DB_SERVICES); do \
		$(MAKE) --no-print-directory _migrations-check s=$$svc || { status=1; break; }; \
	done; $(db_test_down); exit $$status

# Variáveis exportadas valem mais que o .env lido pelo pydantic
_migrations-check:
	$(need_db_s)@echo "==> $(s)"; \
	export DB_HOST=127.0.0.1 DB_PORT=3317 DB_MIGRATOR_USER=migrator DB_MIGRATOR_PASSWORD=m \
		DB_NAME=$(or $(DB_NAME_$(s)),veriditi) DB_USER=$(DB_USER_$(s)); \
	a="uv run alembic -c services/$(s)/alembic.ini"; \
	n=$$($$a heads | grep -c .); [ $$n -le 1 ] || { echo "$(s): $$n heads"; exit 1; }; \
	$$a upgrade head && $$a check && $$a downgrade base && $$a upgrade head || exit 1; \
	vt=$$(docker exec $(DB_TEST) mysql -uroot -proot -N -e "SELECT COUNT(*) FROM \
		information_schema.TABLES WHERE TABLE_SCHEMA='$$DB_NAME' \
		AND TABLE_NAME='alembic_version_$(s)'" 2>/dev/null); \
	[ "$$vt" = 1 ] || { echo "$(s): falta alembic_version_$(s) em $$DB_NAME (VERSION_TABLE)"; exit 1; }

lint: ## ruff, mypy e lint/typecheck da web
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy services/*/src libs/python/*/src
	npm run lint:web
	npm run typecheck:web

format: ## Formata o código Python
	uv run ruff check --fix .
	uv run ruff format .

check: lint test ## lint + test
