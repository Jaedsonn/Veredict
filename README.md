# Veriditi

Plataforma web para coleta, autenticação e preservação de evidências digitais auditáveis com valor probatório, construída segundo o estilo arquitetural **Service-Based Architecture (SBA) / Arquitetura Baseada em Serviços**.

## Estrutura do Monorepo (SBA)

```
veriditi/
├── apps/
│   └── web/                  # Next.js 16 (App Router, TS, Tailwind — BFF)
├── services/
│   └── auth/                 # Serviço de Automação / Autenticação (FastAPI + SQLAlchemy 2 + Alembic)
│       ├── src/auth_service/ # Camadas: api, use_cases, domain, ports, adapters
│       ├── migrations/       # Alembic isolado (alembic_version_auth)
│       ├── tests/            # Testes unitários e de integração (S1-07 a S1-10)
│       └── Dockerfile        # Container próprio do serviço
├── libs/
│   └── python/common/        # Infra compartilhada: settings, db, health, logging JSON,
│                             # request-id, segurança interna, AuditLogger e Notifier
├── docs/
│   ├── adr/                  # Architecture Decision Records (ADRs)
│   ├── banco-de-dados.md     # Modelo de dados, posse por serviço e privilégios
│   ├── requisitos.md         # RF01–RF21, RNF01–RNF08, escopo da Sprint 1 (30%) e rastreabilidade
│   ├── solid.md              # Onde e por que os princípios SOLID foram aplicados + alinhamento SBA
│   └── uso-de-ia.md          # Indicativo de uso de IA (ferramenta, modelo e finalidade)
├── packages/                 # (futuro) pacotes TS compartilhados
├── docker-compose.yml
├── Makefile
├── package.json              # npm workspaces
└── pyproject.toml            # uv workspace (um único uv.lock)
```

## Arquitetura Baseada em Serviços (SBA) — Síntese

- **Top 4 Características Arquiteturais**: `Segurança`, `Confiabilidade`, `Auditabilidade`, `Recuperabilidade`.
- **Componentes**:
  - `Serviço de Automação` (Autenticação — `services/auth`)
  - `Serviço de Pagamento` (`services/payment`)
  - `Serviço de Notificações` (`services/notification`)
  - `Serviço de Captura` (`services/capture`)
  - `Serviço de Armazenamento` (`services/storage`)
  - `Serviço de Monitoramento` (`services/monitoring`)
  - `API Gateway` (`API Getaway` — `services/gateway`)
- **Táticas**:
  - *Segurança*: Verificação de Email, Recuperação de Conta por EMail, Verificação em Duas Etapas.
  - *Confiabilidade*: Arquitetura Baseada em Serviços, Divisão do Banco de Dados.
  - *Recuperabilidade*: Geração de Logs Estruturados, Divisão dos Bancos de Dados, Arquitetura Baseada em Serviços.
  - *Auditabilidade*: Geração de Logs Estruturados.
- **Decisões**: Aplicação Web, Verificação do Email do Usuario, Recuperação da Conta Por Link Via Email, Verificação em Multiplas Etapas, Divisão dos Bancos de Dados, Confirmação da Integridade das Provas Por Hash, Geração de Logs Estruturados, Pagamento Por Serviço Externo.

## Documentação

| Documento | Conteúdo |
| --------- | -------- |
| [Requisitos e escopo](docs/requisitos.md) | RF01–RF21, RNF01–RNF08, escopo da Sprint 1 (30%) e rastreabilidade |
| [ADRs](docs/adr/README.md) | Decisões de arquitetura e desvios em relação ao documento original |
| [Banco de dados](docs/banco-de-dados.md) | Modelo de dados, posse por serviço e privilégios |
| [Princípios SOLID e SBA](docs/solid.md) | Onde e por que cada princípio SOLID foi utilizado em `services/auth` e `libs/python/common` |
| [Indicativo de Uso de IA](docs/uso-de-ia.md) | Transparência sobre qual IA foi utilizada, qual modelo e qual a finalidade |

## Pré-requisitos

Node 22+, [uv](https://docs.astral.sh/uv/), Docker com Compose.

## Setup

```bash
make install   # npm install + uv sync + cria .env
make up        # sobe mysql + migrations + serviços + web
```

| O quê           | URL                              |
| --------------- | -------------------------------- |
| Web             | http://localhost:3000            |
| Health agregado | http://localhost:3000/api/health |
| API auth (docs) | http://localhost:8001/docs       |
| MySQL (host)    | localhost:3307                   |

### Desenvolvimento com hot reload

```bash
make db          # só o MySQL no Docker
make migrate     # aplica migrations (services/auth)
make dev-auth    # terminal 1 (serviço de autenticação na porta 8001)
make dev-web     # terminal 2
```

`make help` lista todos os comandos.

### Web sem o backend (gateway mock)

Enquanto o API Gateway (#11) não existe, a web roda contra um mock em memória
que implementa os contratos da Sprint 1 (cadastro, verificação, login, refresh,
logout e perfil):

```bash
npm run mock:gateway   # terminal 1 — http://localhost:8080 (códigos de verificação aparecem no console)
npm run dev:web        # terminal 2 — http://localhost:3000 (usa GATEWAY_URL, padrão http://localhost:8080)
```

`MOCK_ACCESS_TTL_S=20 npm run mock:gateway` encurta o access token para testar a renovação de sessão.
