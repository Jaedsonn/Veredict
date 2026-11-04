# Veriditi

```
veriditi/
├── apps/
│   └── web/                  # Next.js 16 (App Router, TS, Tailwind)
├── services/
│   └── users/                # Serviço FastAPI (exemplo/template)
│       ├── src/users_service/
│       ├── migrations/       # Alembic do serviço
│       ├── tests/
│       └── Dockerfile
├── libs/
│   └── python/common/        # Infra compartilhada: settings, conexão, health
├── packages/                 # (futuro) pacotes TS compartilhados
├── docker-compose.yml
├── Makefile
├── package.json              # npm workspaces
└── pyproject.toml            # uv workspace (um único uv.lock)
```

## Pré-requisitos

Node 22+, [uv](https://docs.astral.sh/uv/), Docker com Compose.

## Setup

```bash
make install   # npm install + uv sync + cria .env
make up        # sobe mysql + migrations + serviços + web
```

| O quê            | URL                              |
| ---------------- | -------------------------------- |
| Web              | http://localhost:3000            |
| Health agregado  | http://localhost:3000/api/health |
| API users (docs) | http://localhost:8001/docs       |
| MySQL (host)     | localhost:3307                   |

### Desenvolvimento com hot reload

```bash
make db          # só o MySQL no Docker
make migrate     # aplica migrations
make dev-users   # terminal 1
make dev-web     # terminal 2
```

`make help` lista todos os comandos.

## Criando um novo serviço ( Leia isso se você é backend ou está trabalhando no backend)

1. Copie `services/users` para `services/<nome>` e renomeie o pacote
   (`<nome>-service` / `<nome>_service`) no `pyproject.toml` e nos imports.
2. Em `migrations/env.py`, troque `VERSION_TABLE` para `alembic_version_<nome>`
   e apague as migrations antigas de `migrations/versions/`.
3. Adicione o pacote às `dependencies` e `[tool.uv.sources]` do `pyproject.toml`
   da raiz e rode `uv sync`.
4. Adicione `<nome>-migrate` e `<nome>` no `docker-compose.yml` e a URL em
   `apps/web/src/lib/services.ts`.
