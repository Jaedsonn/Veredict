# Veriditi

```
veriditi/
├── apps/
│   └── web/                  # Next.js 16 (App Router, TS, Tailwind)
├── services/
│   ├── gateway/              # API Gateway (sem banco), único backend com porta pública
│   ├── auth/                 # Autenticação (banco veriditi)
│   │   ├── src/auth_service/
│   │   ├── migrations/       # Alembic do serviço (alembic_version_auth)
│   │   ├── tests/
│   │   └── Dockerfile
│   ├── notification/         # Notificações por e-mail (banco veriditi)
│   └── monitoring/           # Trilha de auditoria (banco veriditi_logs)
├── libs/
│   └── python/common/        # Infra compartilhada: settings, conexão, tipos, health
├── docker/mysql/init/        # Bancos e usuários MySQL (só rodam com o volume vazio)
├── packages/                 # (futuro) pacotes TS compartilhados
├── docker-compose.yml
├── Makefile
├── package.json              # npm workspaces
└── pyproject.toml            # uv workspace (um único uv.lock)
```

## Documentação

| Documento | Conteúdo |
| --------- | -------- |
| [Requisitos e escopo](docs/requisitos.md) | RF01–RF21, RNF01–RNF08, escopo da Sprint 1 (30%) e rastreabilidade |
| [ADRs](docs/adr/README.md) | Decisões de arquitetura e desvios em relação ao documento original |
| [Banco de dados](docs/banco-de-dados.md) | Modelo de dados, posse por serviço e privilégios |

## Pré-requisitos

Node 22+, [uv](https://docs.astral.sh/uv/), Docker com Compose.

## Setup

```bash
make install   # npm install + uv sync + cria .env
make up        # sobe mysql + migrations + serviços + web
```

| O quê                     | URL                                |
| ------------------------- | ---------------------------------- |
| Web                       | http://localhost:3000              |
| Health agregado (web)     | http://localhost:3000/api/health   |
| Gateway                   | http://localhost:8080/health/ready |
| Mailpit (e-mails de dev)  | http://localhost:8025              |
| Mailpit SMTP              | localhost:1025 (`MAILPIT_SMTP_PORT`) |
| MySQL (host)              | localhost:3307                     |

As portas do host vêm do `.env` (`WEB_PORT`, `GATEWAY_PORT`, `MAILPIT_UI_PORT`,
`MAILPIT_SMTP_PORT`, `DB_PORT`). `auth`, `notification` e `monitoring` não
publicam porta: só o gateway e a web são acessíveis de fora da rede do compose.
MySQL e Mailpit ficam presos a `127.0.0.1`. O SMTP do Mailpit também é
publicado, por decisão consciente: sem ele o `make dev s=notification` fora do
Docker não teria onde entregar e-mail. Ao mudar o `MAILPIT_SMTP_PORT`, mude
também o `SMTP_PORT` do `.env`, que é a porta usada pelo notification fora do
Docker. Dentro do compose o notification usa sempre `mailpit:1025`.

### Banco

Os scripts de `docker/mysql/init` (bancos `veriditi` e `veriditi_logs`,
usuário `migrator` e um usuário de runtime por serviço) **só rodam com o volume
vazio**. Ao atualizar para esta versão, ou ao mudar o init:

1. Atualize o `.env` a partir do `.env.example`. As senhas agora são por
   usuário (`DB_MIGRATOR_PASSWORD`, `AUTH_DB_PASSWORD`,
   `NOTIFICATION_DB_PASSWORD`, `LOGS_DB_PASSWORD`), e o compose recusa subir
   sem elas. Quem não tinha `.env` pode rodar `make install`.
2. Recrie o volume e suba de novo:

   ```bash
   make reset     # docker compose down -v --remove-orphans
   make up
   ```

`make down`, `make reset` e `make logs` funcionam mesmo com o `.env` antigo
(o `.env.example` preenche só as senhas que faltam), para dar para derrubar o
stack anterior.

As imagens se chamam `veriditi-<serviço>` em qualquer projeto do compose: dois
clones lado a lado (`COMPOSE_PROJECT_NAME` diferente) compartilham a tag, e o
último build vence.

Se o `mysql` ficar `unhealthy` logo na primeira subida, o init falhou (veja
`make logs`, geralmente senha faltando ou com `'`/`\`): corrija o `.env` e rode
`make reset`, porque o init não roda de novo sobre um volume já criado.

O modelo de dados está em [`docs/banco-de-dados.md`](docs/banco-de-dados.md).

### Desenvolvimento com hot reload

```bash
make db                          # só o MySQL no Docker
make migrate                     # migrations de todos os serviços (ou s=auth)
make dev s=auth                  # terminal 1 (s=gateway|auth|notification|monitoring)
make dev-web                     # terminal 2
make migration s=auth m="msg"    # nova revisão autogerada
make test                        # testes sem MySQL (ou s=auth)
make db-test                     # contrato + migrations num MySQL descartável (porta 3317)
```

| Serviço      | `make dev` |
| ------------ | ---------- |
| gateway      | 8080       |
| auth         | 8001       |
| notification | 8002       |
| monitoring   | 8003       |

`make help` lista todos os comandos.

### Logs e X-Request-ID

Os serviços escrevem uma linha JSON por evento no stdout, inclusive as do
uvicorn ([ADR-012](docs/adr/0012-geracao-de-logs-estruturados.md)):

```json
{"method": "GET", "path": "/nao-existe", "status_code": 404, "duration_ms": 1.38, "event": "request_finished", "request_id": "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55", "level": "info", "logger": "veriditi_common.middleware", "service": "gateway", "timestamp": "2026-11-12T05:26:22.960365Z"}
```

Toda resposta traz o `X-Request-ID`: o do cliente, se for um UUID válido, ou um
UUID4 novo. Para seguir uma requisição, `make logs | grep <request_id>`. O
acesso a `/health/*` só aparece com `LOG_LEVEL=DEBUG`. Chaves que contêm
`password`, `secret`, `token`, `cookie`, `authorization`, `private_key`,
`api_key` ou `otp`, e `code`/`*_code`, saem como `[redacted]`, inclusive em
pares de headers. Por isso o código de erro de negócio vai em `error_code`
(`status_code` e `error_code` não são redigidos).

Os erros seguem `{"detail": {"code": "...", "message": "...", ...extras}}`, o
formato lido por `apps/web/src/lib/errors.ts`; o 422 de validação mantém o
formato do FastAPI. Falhas de entrega ao monitoring e ao notification não
quebram a requisição: aparecem no log com `audit_fallback=true` e
`notification_fallback=true`.

| Variável | Uso |
| -------- | --- |
| `LOG_LEVEL` | `DEBUG`, `INFO` (padrão), `WARNING` ou `ERROR` |
| `INTERNAL_API_TOKEN` | Mínimo de 16 caracteres; auth, notification e monitoring não sobem sem ele |
| `MONITORING_URL`, `NOTIFICATION_URL` | Só no `make dev`; o compose fixa `http://monitoring:8000` e `http://notification:8000` |

### Web sem o backend (gateway mock)

Enquanto o roteamento do API Gateway (#11) não existe, a web roda contra um mock em memória
que implementa os contratos da Sprint 1 (cadastro, verificação, login, refresh,
logout e perfil):

```bash
npm run mock:gateway   # terminal 1 — http://localhost:8080 (códigos de verificação aparecem no console)
npm run dev:web        # terminal 2 — http://localhost:3000 (usa GATEWAY_URL, padrão http://localhost:8080)
```

`MOCK_ACCESS_TTL_S=20 npm run mock:gateway` encurta o access token para testar a renovação de sessão.

O mock usa a mesma porta 8080 do gateway do compose: pare o stack (`make down`) antes de rodá-lo.
