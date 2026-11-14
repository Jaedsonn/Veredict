# Princípios SOLID e Alinhamento Arquitetural (SBA) no Veriditi (`services/auth`)

Este documento descreve onde e por que cada um dos cinco princípios **SOLID**, o **PEP 8 (Python Style Guide)** e as boas práticas de Engenharia de Software foram aplicados na implementação do **Serviço de Automação / Autenticação** (`services/auth`, Issues **#7**, **#8**, **#9** e **#10**), integrado à biblioteca compartilhada (`libs/python/common`, Issue **#4** / PR **#53**), em estrita conformidade com a **Arquitetura Baseada em Serviços (Service-Based Architecture — SBA)** do projeto. Os links de código apontam para `arquivo#Lnn`; os exemplos de OCP, LSP, ISP e DIP incluem também o `gateway` e o `notification`. Cada princípio traz "Sem isso:", o que aconteceria sem ele.

---

## 1. Alinhamento com a Arquitetura Baseada em Serviços (SBA)

O Veriditi adota o estilo arquitetural **Service-Based Architecture (SBA) / Arquitetura Baseada em Serviços**, estruturado em torno dos seguintes elementos do documento arquitetural:

### 1.1 Top 4 Características Arquiteturais
1. **Segurança**
2. **Confiabilidade**
3. **Auditabilidade**
4. **Recuperabilidade**

### 1.2 Componentes da Arquitetura (SBA)
- **API Gateway (`API Getaway`)**: ponto único de entrada HTTP para a aplicação Web, responsável pela validação centralizada de JWT e propagação de contexto (`X-Request-ID`, `X-User-Id`, `X-Internal-Token`).
- **Serviço de Automação (Autenticação — `services/auth`)**: componente responsável por gestão de identidade, cadastro (`RF01`), verificação de e-mail (`RF02`), sessão JWT RS256 e rotação de refresh token (`RF03`) e gestão de perfil e senha (`RF06`).
- **Serviço de Pagamento (`services/payment`)**: gestão de pacotes de créditos, checkout PIX e razão contábil (*ledger*).
- **Serviço de Notificações (`services/notification`)**: disparo transacional de e-mails com idempotência e retentativas.
- **Serviço de Captura (`services/capture`)**: automação do isolamento e coleta de provas digitais (screenshots e vídeos de navegação).
- **Serviço de Armazenamento (`services/storage`)**: preservação imutável de evidências com verificação de integridade por hash SHA-256.
- **Serviço de Monitoramento (`services/monitoring`)**: ingestão e preservação append-only de eventos de auditoria e logs operacionais em banco dedicado (`veriditi_logs`).

### 1.3 Táticas Arquiteturais Mapeadas no Código
- **Segurança**:
  - *Verificação de Email*: implementada em [`verify_email.py`](../services/auth/src/auth_service/use_cases/verify_email.py#L40) e [`verification_code.py`](../services/auth/src/auth_service/domain/verification_code.py#L9) com códigos CSPRNG de 6 dígitos e HMAC-SHA256 com *pepper*.
  - *Recuperação de Conta por EMail*: ponto de extensão preparado no domínio e nas portas de notificação/auditoria para a Sprint 2 (`#19`).
  - *Verificação em Duas Etapas*: preparada no resultado polimórfico `LoginResult` ([`entities.py`](../services/auth/src/auth_service/domain/entities.py#L115)) e no enum `VerificationPurpose.MFA` ([`models.py`](../services/auth/src/auth_service/models.py#L42)).
- **Confiabilidade**:
  - *Arquitetura Baseada em Serviços*: isolamento de falhas nos clientes HTTP internos ([`audit.py`](../libs/python/common/src/veriditi_common/audit.py#L197) e [`notifications.py`](../libs/python/common/src/veriditi_common/notifications.py#L43)), garantindo que indisponibilidades temporárias não derrubem o fluxo do usuário.
  - *Divisão do Banco de Dados*: segregação de posse e privilégios mínimos por serviço (`auth_svc` sem `DELETE` em `users`, conforme [`migrations.py`](../libs/python/common/src/veriditi_common/migrations.py#L78) e [`docs/banco-de-dados.md`](banco-de-dados.md)).
- **Recuperabilidade**:
  - *Geração de Logs Estruturados*: logs JSON padronizados via `structlog` com correlação por `request_id` ([`logging.py`](../libs/python/common/src/veriditi_common/logging.py#L285)).
  - *Divisão dos Bancos de Dados*: separação entre o Banco Central (`veriditi`), o Log Storage (`veriditi_logs`) e o Object Storage de evidências.
  - *Arquitetura Baseada em Serviços*: desacoplamento entre componentes de domínio com estados independentes e migrações próprias por serviço (`alembic_version_auth`).
- **Auditabilidade**:
  - *Geração de Logs Estruturados*: emissão sistemática de eventos de auditoria imutáveis (`AuditEvent`) com sanitização automática de dados sensíveis ([`audit.py`](../libs/python/common/src/veriditi_common/audit.py#L127)).

### 1.4 Decisões Arquiteturais Contempladas
- **Aplicação Web** (`apps/web` consumindo o `API Gateway`).
- **Verificação do Email do Usuario** (`POST /auth/verify-email` e `POST /auth/verify-email/resend`, [#8](https://github.com/Jaedsonn/Veredict/issues/8)).
- **Recuperação da Conta Por Link Via Email** (contratos e infraestrutura de notificação/auditoria preparados para a Sprint 2, [#19](https://github.com/Jaedsonn/Veredict/issues/19)).
- **Verificação em Multiplas Etapas** (contrato de login extensível via `MfaRequiredResult` / `MfaSetupRequiredResult` e `purpose = 'mfa'`, [#18](https://github.com/Jaedsonn/Veredict/issues/18)).
- **Divisão dos Bancos de Dados** (isolamento de posse por serviço com `alembic_version_auth` e privilégios restritos por tabela).
- **Confirmação da Integridade das Provas Por Hash** (padrão `HashHex` em `CHAR(64) ascii_bin` compartilhado em `veriditi_common.db_types`).
- **Geração de Logs Estruturados** (`veriditi_common.logging` e `veriditi_common.audit`, [#4](https://github.com/Jaedsonn/Veredict/issues/4)).
- **Pagamento Por Serviço Externo** (isolamento do domínio de autenticação em relação ao componente `Serviço de Pagamento`).

---

## 2. Visão Geral da Estrutura Interna (`Ports & Adapters`)

Dentro da **Arquitetura Baseada em Serviços (SBA)**, o serviço `services/auth` organiza seu código segundo a Arquitetura Limpa / Hexagonal (*Ports & Adapters*), separando responsabilidades em quatro camadas:

```mermaid
flowchart TD
    API["Camada HTTP (FastAPI Routers)<br/>api/auth.py, api/profile.py, schemas.py"]
    UC["Camada de Aplicação (Casos de Uso)<br/>use_cases/register_user.py, verify_email.py,<br/>authenticate_user.py, profile.py"]
    PORTS["Camada de Portas (Abstrações / Protocols)<br/>ports.py + veriditi_common (AuditLogger, Notifier)"]
    DOM["Camada de Domínio Puro<br/>domain/entities.py, errors.py,<br/>password_policy.py, verification_code.py"]
    ADAPT["Camada de Adaptadores (Infraestrutura)<br/>adapters/repositories.py, password_hasher.py,<br/>token_issuer.py, clock.py"]

    API --> UC
    UC --> PORTS
    UC --> DOM
    ADAPT -. implementa .-> PORTS
```

### 2.1 Diagrama de classes do auth

As setas tracejadas com ponta vazada são "implementa"; as tracejadas simples são "depende de". Todos os casos de uso também recebem `Clock` e `AuditLogger` (omitidos das setas para o diagrama ficar legível). `RegisterUser` e `VerifyEmail` recebem ainda o `Notifier`, e `AuditLogger` e `Notifier` vêm de `veriditi_common`. Faltam do diagrama `ResendVerificationCode`, `RefreshSession` e `LogoutUser`, que seguem o mesmo padrão.

```mermaid
classDiagram
    direction LR

    class RegisterUser
    class VerifyEmail
    class AuthenticateUser
    class GetProfile
    class UpdateProfile
    class ChangePassword

    class PasswordHasher {
        <<Protocol>>
    }
    class TokenIssuer {
        <<Protocol>>
    }
    class UserRepository {
        <<Protocol>>
    }
    class VerificationCodeRepository {
        <<Protocol>>
    }
    class RefreshTokenRepository {
        <<Protocol>>
    }
    class Clock {
        <<Protocol>>
    }
    class Notifier {
        <<Protocol>>
    }
    class AuditLogger {
        <<Protocol>>
    }

    class Argon2PasswordHasher
    class PyJwtTokenIssuer
    class SqlAlchemyUserRepository
    class SqlAlchemyVerificationCodeRepository
    class SqlAlchemyRefreshTokenRepository
    class SystemClock
    class FakeClock
    class HttpNotifier
    class HttpAuditLogger

    RegisterUser ..> UserRepository
    RegisterUser ..> VerificationCodeRepository
    RegisterUser ..> PasswordHasher
    RegisterUser ..> Notifier
    VerifyEmail ..> UserRepository
    VerifyEmail ..> VerificationCodeRepository
    VerifyEmail ..> Notifier
    AuthenticateUser ..> UserRepository
    AuthenticateUser ..> RefreshTokenRepository
    AuthenticateUser ..> PasswordHasher
    AuthenticateUser ..> TokenIssuer
    GetProfile ..> UserRepository
    UpdateProfile ..> UserRepository
    ChangePassword ..> UserRepository
    ChangePassword ..> RefreshTokenRepository
    ChangePassword ..> PasswordHasher
    ChangePassword ..> TokenIssuer

    Argon2PasswordHasher ..|> PasswordHasher
    PyJwtTokenIssuer ..|> TokenIssuer
    SqlAlchemyUserRepository ..|> UserRepository
    SqlAlchemyVerificationCodeRepository ..|> VerificationCodeRepository
    SqlAlchemyRefreshTokenRepository ..|> RefreshTokenRepository
    SystemClock ..|> Clock
    FakeClock ..|> Clock
    HttpNotifier ..|> Notifier
    HttpAuditLogger ..|> AuditLogger
```

---

## 3. Onde e Por Quê cada Princípio SOLID foi Aplicado

### 3.1 SRP — *Single Responsibility Principle* (Princípio da Responsabilidade Única)

> *"Um módulo ou classe deve ter um, e apenas um, motivo para mudar."*

| Onde foi aplicado | Responsabilidade única | Por que foi utilizado (motivação de negócio e arquitetura) |
| :--- | :--- | :--- |
| [`PasswordPolicy`](../services/auth/src/auth_service/domain/password_policy.py#L65) | Validar exclusivamente as regras de complexidade de senha (mínimo de 10 caracteres, ao menos 1 letra e 1 número). | Isola mudanças na política de senha (RF01 / RNF01) do algoritmo de hash e da persistência. Se a regra de complexidade mudar, nem o caso de uso nem o repositório precisam ser alterados. **Sem isso:** a regra de complexidade ficaria espalhada entre o caso de uso e o hash, e mudar o mínimo de caracteres exigiria editar cadastro e troca de senha ao mesmo tempo. |
| [`Argon2PasswordHasher`](../services/auth/src/auth_service/adapters/password_hasher.py#L10) | Calcular e verificar hashes criptográficos Argon2id, incluindo verificação *dummy* em tempo constante. | Separa os parâmetros criptográficos (`time_cost`, `memory_cost`, `parallelism`) da lógica de login e cadastro, permitindo calibrar segurança/performance em um único ponto. **Sem isso:** calibrar o custo do Argon2 exigiria editar a lógica de login, e um erro ali quebraria o fluxo de autenticação inteiro. |
| [`VerificationCodeService`](../services/auth/src/auth_service/domain/verification_code.py#L9) | Gerar códigos CSPRNG de 6 dígitos (`secrets.randbelow`), calcular `HMAC-SHA256` com `VERIFICATION_PEPPER` e comparar hashes em tempo constante (`hmac.compare_digest`). | Centraliza a criptografia de códigos de verificação (RF02), garantindo que o código em texto puro nunca vaze para a camada de persistência. **Sem isso:** cada caso de uso reimplementaria a geração e a comparação do código, e um `==` no lugar de `compare_digest` abriria um canal de tempo. |
| [`PyJwtTokenIssuer`](../services/auth/src/auth_service/adapters/token_issuer.py#L12) | Emitir Access Tokens JWT assinados com `RS256` (`sub`, `email`, `iat`, `exp`, `iss`, `aud`, `jti`, `sid`) e gerar/hashear Refresh Tokens opacos de 32 bytes com `SHA-256`. | Isola a biblioteca `PyJWT` e a gestão de chaves assimétricas RSA da lógica de rotação de sessão e detecção de reuso. **Sem isso:** a rotação de sessão importaria PyJWT e as chaves RSA, e trocar de algoritmo ou de biblioteca tocaria a regra de reuso de refresh token. |
| [`RegisterUser`](../services/auth/src/auth_service/use_cases/register_user.py#L38), [`VerifyEmail`](../services/auth/src/auth_service/use_cases/verify_email.py#L40), [`AuthenticateUser`](../services/auth/src/auth_service/use_cases/authenticate_user.py#L56), [`ChangePassword`](../services/auth/src/auth_service/use_cases/profile.py#L110) | Cada classe representa um único caso de uso de negócio. | Evita uma classe monolítica `AuthService` ("God Object") que misturaria cadastro, OTP, JWT, rotação de refresh token e edição de perfil. **Sem isso:** um único `AuthService` acumularia dezenas de dependências, e mexer no perfil reabriria cadastro e login nos mesmos testes. |
| [`redact_sensitive`](../libs/python/common/src/veriditi_common/logging.py#L199) / [`AuditEvent`](../libs/python/common/src/veriditi_common/audit.py#L127) | Sanitizar recursivamente logs e metadados removendo chaves sensíveis (`password`, `token`, `code`, `secret`). | Garante em um único ponto que nenhum serviço exponha segredos nos logs ou eventos de auditoria enviados ao `Serviço de Monitoramento`. **Sem isso:** cada serviço escreveria a própria limpeza de logs, e bastaria um esquecer uma chave para vazar senha ou token. |

---

### 3.2 OCP — *Open/Closed Principle* (Princípio Aberto/Fechado)

> *"Entidades de software devem estar abertas para extensão, mas fechadas para modificação."*

| Onde foi aplicado | Ponto de extensão | Por que foi utilizado |
| :--- | :--- | :--- |
| [`LoginResult`](../services/auth/src/auth_service/domain/entities.py#L115) (`AuthenticatedResult \| MfaRequiredResult \| MfaSetupRequiredResult`) | Tipo união discriminado retornado por `AuthenticateUser.execute()`. | Na Sprint 1 (#9), o login conclui emitindo `AuthenticatedResult`. Na Sprint 2 (#18 — *Verificação em Duas Etapas / Multiplas Etapas*), o fluxo passa a retornar `MfaRequiredResult` ou `MfaSetupRequiredResult` sem quebrar a assinatura do caso de uso nem modificar os consumidores existentes. **Sem isso:** trocar o retorno do login para o fluxo de MFA mudaria a assinatura de `AuthenticateUser` e obrigaria a reeditar todos os consumidores. |
| [`VerificationPurpose`](../services/auth/src/auth_service/models.py#L42) (`EMAIL_VERIFICATION`, `MFA`) | Coluna `purpose` parametrizada nos métodos de `VerificationCodeRepository`. | Permite reutilizar a mesma estrutura e repositório de códigos de 6 dígitos tanto para confirmação de e-mail (#8) quanto para o segundo fator por e-mail (#18), sem alterar as queries existentes. **Sem isso:** o segundo fator pediria outra tabela e outro repositório, duplicando as queries de código. |
| [`TemplateRegistry`](../services/notification/src/notification_service/registry.py#L18) (`TemplateSpec`, montado em [`build_registry()`](../services/notification/src/notification_service/catalog.py#L58)) | Um e-mail novo é um `TemplateSpec` a mais no catálogo, com a pasta `templates/<nome>/` e o schema do `data`. | O caso de uso `SendNotification` só pergunta ao registry se o template existe e se o `data` é válido; ele não conhece nenhum e-mail pelo nome. **Sem isso:** haveria um `if template == ...` por e-mail dentro do caso de uso, e cada e-mail novo editaria código que já funciona. |
| [`ROUTES`](../services/gateway/src/gateway_service/routes.py#L11) (cada item é uma [`Route`](../services/gateway/src/gateway_service/domain.py#L29)) | Um endpoint ou serviço novo é uma linha nova na tabela, validada na subida. | O proxy, o rate limit e o JWT leem a tabela e não mudam: `RouteTable` recusa duplicata, upstream desconhecido e caminho inseguro. **Sem isso:** o roteamento seria um `if/elif` dentro do gateway, e cada serviço da Sprint 2 (pagamento, captura) editaria o código que protege a entrada do sistema. |
| [`AuditLogger`](../libs/python/common/src/veriditi_common/audit.py#L193) e [`Notifier`](../libs/python/common/src/veriditi_common/notifications.py#L39) | Novos transportes (ex.: Outbox / Redis Streams na Sprint 2, #37) podem ser adicionados criando novas classes que implementam o `Protocol`. | Os casos de uso (`RegisterUser`, `VerifyEmail`, `AuthenticateUser`, `UpdateProfile`, `ChangePassword`) estão **fechados para modificação** quando o transporte evoluir de HTTP *fire-and-forget* para mensageria assíncrona. **Sem isso:** trocar o HTTP por um outbox exigiria editar cada caso de uso que audita ou notifica. |

---

### 3.3 LSP — *Liskov Substitution Principle* (Princípio da Substituição de Liskov)

> *"Subtipos devem ser substituíveis por seus tipos base sem alterar a corretude do programa."*

| Abstração (`Protocol`) | Implementação de Produção | Implementação de Teste / Fallback | Garantia de Substituibilidade (LSP) |
| :--- | :--- | :--- | :--- |
| [`AuditLogger`](../libs/python/common/src/veriditi_common/audit.py#L193) | `HttpAuditLogger` (envia `POST /internal/events` ao `Serviço de Monitoramento` com degradação graciosa para log estruturado) | `InMemoryAuditLogger` (acumula eventos em memória nos testes) | Ambas respeitam o pré-requisito de sanitização de `AuditEvent` e o pós-requisito de **nunca lançar exceções de transporte** que interrompam a transação principal do usuário. **Sem isso:** se o fake lançasse erro de transporte (ou o real lançasse e derrubasse a requisição), o caso de uso se comportaria diferente em produção e nos testes. |
| [`Notifier`](../libs/python/common/src/veriditi_common/notifications.py#L39) | `HttpNotifier` (envia `POST /internal/notifications` ao `Serviço de Notificações`) | `InMemoryNotifier` (captura notificações enviadas para inspeção do código de 6 dígitos nos testes) | Ambas aceitam `NotificationRequest` com `idempotency_key` e completam de forma resiliente, permitindo testar todo o fluxo de verificação de e-mail (#8) sem servidor SMTP externo. **Sem isso:** os testes do cadastro precisariam de um serviço de notificação no ar para ler o código, ou passariam num fake que não se comporta como o real. |
| [`Clock`](../services/auth/src/auth_service/ports.py#L20) | `SystemClock` ([`clock.py`](../services/auth/src/auth_service/adapters/clock.py#L6)) | `FakeClock` ([`clock.py`](../services/auth/src/auth_service/adapters/clock.py#L13)) | Ambas retornam `datetime` *timezone-aware* em UTC. Substituir `SystemClock` por `FakeClock` permite avançar o tempo (`clock.advance(minutes=16)` ou `seconds=65`) e testar determinísticamente expiração de código (15 min), cooldown de reenvio (60 s) e janela de 1 hora (5 reenvios/h). **Sem isso:** os testes de expiração dariam `sleep` de minutos, ou um fake que devolvesse `datetime` sem fuso quebraria as comparações só nos testes. |
| [`EmailSender`](../services/notification/src/notification_service/ports.py#L21) | [`SmtpEmailSender`](../services/notification/src/notification_service/adapters/smtp_sender.py#L110) (uma conexão SMTP por envio) | [`InMemoryEmailSender`](../services/notification/src/notification_service/adapters/memory_sender.py#L4) (guarda o `OutgoingEmail` em `sent`) e [`FailingEmailSender`](../services/notification/src/notification_service/adapters/memory_sender.py#L14) (subclasse que falha nas primeiras chamadas) | Todas aceitam um `OutgoingEmail` e só sinalizam falha com `EmailDeliveryError`, cujo `permanent` decide se há nova tentativa. O fake troca o SMTP sem que o caso de uso de reenvio perceba. **Sem isso:** a política de 3 tentativas só seria testável com um servidor SMTP real, ou um fake que levantasse outro tipo de erro não seria reconhecido pelo retry. |

---

### 3.4 ISP — *Interface Segregation Principle* (Princípio da Segregação de Interfaces)

> *"Nenhum cliente deve ser forçado a depender de métodos que não utiliza."*

Em vez de criar um repositório genérico monolítico (`AuthRepository`) ou um único serviço de criptografia, as interfaces em [`ports.py`](../services/auth/src/auth_service/ports.py#L71) foram segregadas por coesão funcional:

- **[`UserRepository`](../services/auth/src/auth_service/ports.py#L71)**: apenas operações sobre a entidade `User` (`create`, `get_by_id`, `get_by_email`, `mark_email_verified`, `update_name`, `update_password_hash`).
- **[`VerificationCodeRepository`](../services/auth/src/auth_service/ports.py#L120)**: apenas operações sobre códigos de verificação (`create_and_invalidate_previous`, `get_latest_active`, `get_latest_for_user`, `count_created_since`, `increment_attempts`, `mark_consumed`).
- **[`RefreshTokenRepository`](../services/auth/src/auth_service/ports.py#L180)**: apenas operações sobre sessões de refresh (`create`, `get_by_hash`, `rotate_token`, `revoke`, `revoke_all_for_user`).
- **[`PasswordHasher`](../services/auth/src/auth_service/ports.py#L28)** vs. **[`TokenIssuer`](../services/auth/src/auth_service/ports.py#L42)**: separados para que casos de uso que não emitem JWT (como `RegisterUser` e `VerifyEmail`) não dependam de chaves RSA ou PyJWT, e casos de uso que apenas consultam perfil (`GetProfile`) dependam **exclusivamente** de `UserRepository` ([`profile.py`](../services/auth/src/auth_service/use_cases/profile.py#L50)).
- **Notification**: as portas de [`EmailRenderer`](../services/notification/src/notification_service/ports.py#L15) (um método, `render`), [`EmailSender`](../services/notification/src/notification_service/ports.py#L21) (`send`) e [`NotificationRepository`](../services/notification/src/notification_service/ports.py#L27) (reserva da chave de idempotência) são separadas: o teste do renderer não precisa de SMTP, e o do envio não precisa de banco.

**Sem isso:** `RegisterUser` e `VerifyEmail` receberiam métodos de sessão e JWT que nunca chamam, cada fake de teste teria de implementar a interface inteira, e uma mudança no contrato de refresh token obrigaria a retestar quem só lê o perfil.

---

### 3.5 DIP — *Dependency Inversion Principle* (Princípio da Inversão de Dependência)

> *"Módulos de alto nível não devem depender de módulos de baixo nível. Ambos devem depender de abstrações."*

1. **Casos de uso desacoplados de frameworks**: Nenhum arquivo em `services/auth/src/auth_service/use_cases/` ou `domain/` importa `fastapi`, `sqlalchemy`, `argon2` ou `jwt`. Todos dependem exclusivamente dos `Protocol`s definidos em [`ports.py`](../services/auth/src/auth_service/ports.py#L20) e `veriditi_common`. **Sem isso:** trocar o MySQL ou o Argon2 exigiria editar as regras de negócio, e não haveria como testá-las sem banco.
2. **Injeção de Dependências explícita na borda HTTP**: O módulo [`dependencies.py`](../services/auth/src/auth_service/dependencies.py#L112) atua como *Composition Root*, instanciando os adaptadores concretos do auth (`SqlAlchemyUserRepository`, `Argon2PasswordHasher`, `PyJwtTokenIssuer`) e injetando-os nos casos de uso via `Depends` do FastAPI. `BackgroundAuditLogger` ([`audit.py`](../libs/python/common/src/veriditi_common/audit.py#L265)) e `BackgroundNotifier` ([`notifications.py`](../libs/python/common/src/veriditi_common/notifications.py#L95)) são da lib comum: o `dependencies.py` apenas reexporta `get_audit_logger` e `get_notifier`, que os compõem sobre o que está em `app.state`. **Sem isso:** cada caso de uso montaria os próprios adaptadores, e a troca de uma implementação teria de ser repetida em todos.
3. **Facilidade de teste e substituição**: Nos testes ([`conftest.py`](../services/auth/tests/conftest.py#L72)), `app.state.audit_logger`, `app.state.notifier` e `app.state.clock` são substituídos por implementações em memória sem usar *monkeypatching* invasivo. **Sem isso:** os testes só passariam com `monkeypatch` de módulos ou com serviços reais no ar.
4. **Gateway**: [`build_gateway`](../services/gateway/src/gateway_service/dependencies.py#L24) é o *composition root* e recebe `limiter: RateLimiter` e `verifier: JwtVerifier` ([`ports.py`](../services/gateway/src/gateway_service/ports.py#L15)); [`AdmitRequest`](../services/gateway/src/gateway_service/use_cases/admit_request.py#L54) só conhece essas portas, e o `InMemoryTokenBucket` é o adaptador de hoje. **Sem isso:** trocar o rate limit em memória pelo Redis da Sprint 2 exigiria editar a regra de admissão, e os testes do JWT precisariam de chaves RSA reais.
5. **Notification**: [`get_send_notification`](../services/notification/src/notification_service/dependencies.py#L28) monta o `SendNotification` com `registry`, `renderer`, `sender`, `notifications` e `scheduler` que vêm do `app.state`, e o caso de uso só enxerga os `Protocol`s de [`ports.py`](../services/notification/src/notification_service/ports.py#L15). **Sem isso:** o caso de uso criaria o cliente SMTP e a sessão do banco, e o teste de retentativa dependeria de um SMTP e de um MySQL no ar.

---

## 4. Style Guide Python (PEP 8) e Boas Práticas de Engenharia de Software

- **Conformidade com PEP 8 e Tipagem Estrita**:
  - Verificação automatizada com **Ruff** (`select = ["E", "F", "I", "B", "UP", "ASYNC", "SIM"]`, `line-length = 100`) e **Mypy** para checagem estática de tipos em Python 3.12+.
  - Uso de `dataclass(frozen=True, slots=True)` para objetos de valor e comandos imutáveis, reduzindo consumo de memória e prevenindo mutações acidentais.
- **Segurança por Design (*Security by Design*)**:
  - Comparações de segredos em tempo constante via `hmac.compare_digest` (no token interno `X-Internal-Token` e no código de verificação de e-mail).
  - Prevenção de enumeração de contas no login (`verify_dummy` executa Argon2id mesmo quando o e-mail não existe) e no reenvio de código (`POST /auth/verify-email/resend` retorna `202 Accepted` para e-mails inexistentes ou já verificados).
  - Prevenção de *Mass Assignment* em `PATCH /me` (`ProfileUpdate` aceita apenas `name` com `extra="ignore"`, ignorando `email`, `status`, etc.).
  - Detecção de reuso de Refresh Token (*Refresh Token Rotation*): se um token já rotacionado (`revoke_reason = 'rotated'`) for reapresentado, o serviço revoga **todas** as sessões ativas do usuário (`revoke_reason = 'reuse_detected'`) e emite o evento crítico `auth.session.refresh_reuse_detected`.
