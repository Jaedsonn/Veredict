# Indicativo de Uso de Inteligência Artificial (Transparência Acadêmica e Técnica)

Em conformidade com as diretrizes de transparência da disciplina **MATA62 — Engenharia de Software I (UFBA)** e com as boas práticas de governança de desenvolvimento de software, este documento registra de forma explícita e auditável o uso de ferramentas de Inteligência Artificial Generativa no desenvolvimento das entregas deste repositório.

---

## 1. Identificação da Ferramenta e do Modelo

| Item | Descrição |
| :--- | :--- |
| **Ferramenta / Agente** | **Google Antigravity** (Agente de Engenharia de Software da equipe Google DeepMind) |
| **Modelo Utilizado** | **Gemini 4 Argon (Medium)** |
| **Escopo de Atuação** | Biblioteca compartilhada (`libs/python/common` — Issue **#4**), **Serviço de Automação / Autenticação** (`services/auth` — Issues **#7**, **#8**, **#9** e **#10**), suíte de testes automatizados (Issue **#15**) e documentação técnica de princípios SOLID e alinhamento com a **Arquitetura Baseada em Serviços (SBA)** (Issue **#16**). |

---

## 2. Finalidade do Uso de IA por Entrega

### 2.1 Análise e Rastreabilidade Arquitetural (SBA — Service-Based Architecture)
- **Finalidade**: Leitura cruzada dos documentos normativos do projeto (*Documento de Requisitos — Veridit*, *Documento Arquitetural — Estruturação do Veridit*, [`docs/requisitos.md`](requisitos.md), [`docs/banco-de-dados.md`](banco-de-dados.md) e ADRs vigentes em [`docs/adr/`](adr/README.md)) para garantir que toda a implementação respeitasse a **Arquitetura Baseada em Serviços (SBA)**:
  - **Top 4 Características Arquiteturais**: *Segurança*, *Confiabilidade*, *Auditabilidade* e *Recuperabilidade*.
  - **Componentes**: *Serviço de Automação (Autenticação)*, *Serviço de Pagamento*, *Serviço de Notificações*, *Serviço de Captura*, *Serviço de Armazenamento*, *Serviço de Monitoramento* e *API Gateway (`API Getaway`)*.
  - **Táticas**:
    - *Segurança*: Verificação de Email, Recuperação de Conta por EMail, Verificação em Duas Etapas.
    - *Confiabilidade*: Arquitetura Baseada em Serviços, Divisão do Banco de Dados.
    - *Recuperabilidade*: Geração de Logs Estruturados, Divisão dos Bancos de Dados, Arquitetura Baseada em Serviços.
    - *Auditabilidade*: Geração de Logs Estruturados.
  - **Decisões**: Aplicação Web, Verificação do Email do Usuario, Recuperação da Conta Por Link Via Email, Verificação em Multiplas Etapas, Divisão dos Bancos de Dados, Confirmação da Integridade das Provas Por Hash, Geração de Logs Estruturados, Pagamento Por Serviço Externo.

### 2.2 Implementação da Biblioteca Compartilhada (`libs/python/common` — Issue [S1-04] / #4)
- **Finalidade**: Apoio na estruturação de componentes transversais de observabilidade e comunicação interna:
  - Configuração de logs estruturados em JSON (`structlog`) com propagação de `request_id` ([`logging.py`](../libs/python/common/src/veriditi_common/logging.py) e [`middleware.py`](../libs/python/common/src/veriditi_common/middleware.py)).
  - Validação em tempo constante do token interno `X-Internal-Token` e extração de identidade propagada pelo API Gateway (`X-User-Id`, `X-User-Email`) ([`security.py`](../libs/python/common/src/veriditi_common/security.py)).
  - Clientes HTTP assíncronos resilientes (*fire-and-forget* com degradação graciosa para `stdout`) para o **Serviço de Monitoramento** (`AuditLogger` em [`audit.py`](../libs/python/common/src/veriditi_common/audit.py)) e para o **Serviço de Notificações** (`Notifier` em [`notifications.py`](../libs/python/common/src/veriditi_common/notifications.py)).

### 2.3 Implementação do Serviço de Automação / Autenticação (`services/auth` — Issues [S1-07] a [S1-10])
- **Finalidade**: Geração assistida e estruturação em camadas (*Ports & Adapters*) aplicando rigorosamente os princípios **SOLID** e o **PEP 8**:
  - **[S1-07] (#7)**: Cadastro de usuário (`POST /auth/register`), política de senha forte (`PasswordPolicy`), hash `Argon2id` (`Argon2PasswordHasher`) e migration `0002` ([`20261112_0002_auth_users_columns.py`](../services/auth/migrations/versions/20261112_0002_auth_users_columns.py)).
  - **[S1-08] (#8)**: Verificação de e-mail por código de 6 dígitos (`POST /auth/verify-email`) e reenvio com *cooldown* e limite horário (`POST /auth/verify-email/resend`), persistindo apenas `HMAC-SHA256` com `VERIFICATION_PEPPER` na migration `0003` ([`20261112_0003_create_email_verification_codes.py`](../services/auth/migrations/versions/20261112_0003_create_email_verification_codes.py)).
  - **[S1-09] (#9)**: Autenticação com emissão de JWT `RS256` de 15 min (`POST /auth/login`), rotação de refresh token de 7 dias com detecção de reuso e revogação em cadeia (`POST /auth/refresh`), encerramento de sessão (`POST /auth/logout`) e migration `0004` ([`20261112_0004_create_refresh_tokens.py`](../services/auth/migrations/versions/20261112_0004_create_refresh_tokens.py)).
  - **[S1-10] (#10)**: Consulta (`GET /me`), atualização parcial protegida contra *mass assignment* (`PATCH /me`) e troca de senha com revogação das demais sessões ativas (`POST /me/password`).

### 2.4 Elaboração de Testes Automatizados e Verificação de Qualidade
- **Finalidade**: Escrita de testes unitários e de integração em [`libs/python/common/tests/test_common.py`](../libs/python/common/tests/test_common.py) e [`services/auth/tests/`](../services/auth/tests/), cobrindo cenários de sucesso, erros de validação, expiração temporal com relógio determinístico (`FakeClock`), tentativas máximas de código, detecção de reuso de refresh token e proteção contra *mass assignment*.

---

## 3. Supervisão Humana e Verificação

Todo o código e documentação gerados com auxílio da IA passaram por validação automatizada e revisão técnica:
1. **Análise estática e formatação (PEP 8)**: `ruff check .` e `ruff format --check .` sem alertas.
2. **Checagem estática de tipos**: `mypy services/*/src libs/python/*/src` sem erros.
3. **Execução integral da suíte de testes**: `pytest` validando todos os critérios de aceite das Issues `#4`, `#7`, `#8`, `#9` e `#10` e o contrato de banco de dados em [`docs/banco-de-dados.md`](banco-de-dados.md).
