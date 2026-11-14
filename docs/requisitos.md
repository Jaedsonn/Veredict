# Requisitos e escopo da Sprint 1 (30%)

> **Fonte primária:** documento "Estruturação do Veridit" (Trabalho II de MATA62), transcrito nas [ADRs 001–013](adr/README.md).
> **Planejamento:** épico #40; milestones *Sprint 1 – 30% dos requisitos* e *Sprint 2 – 70% restantes*.
> **Status conferido em:** 2026-11-12, contra o código da `main`. Atualize as colunas de status no fim da sprint (ver [seção 8](#8-como-manter-este-documento)).

Este documento é a fonte da verdade do escopo. Use os IDs (`RF01`, `RNF03`…) nos títulos de issues e PRs para manter a rastreabilidade.

## 1. Visão geral

O Veriditi coleta (captura de tela e gravação de navegação), autentica (hash SHA-256 verificável pelo usuário) e preserva provas digitais com valor probatório. A arquitetura é baseada em serviços ([ADR-005](adr/0005-arquitetura-baseada-em-servicos.md)): API Gateway, Autenticação, Pagamento, Captura, Armazenamento, Notificação e Monitoramento, mais a aplicação Web.

### Objetivo da Sprint 1

Entregar a **fundação** sobre a qual todo o resto se apoia: identidade (Autenticação), porta de entrada única (API Gateway), trilha de auditoria (Monitoramento) e e-mail transacional (Notificação), com a aplicação Web consumindo esses serviços.

**Por que essa fatia:** sem identidade, gateway e auditoria não é possível ter uma captura com valor probatório. Toda prova precisa de um autor autenticado e de um registro imutável de quem fez o quê e quando (ADR-001). Essa fatia também é a menor que roda de ponta a ponta (cadastro → verificação → login → perfil) e cobre três das quatro características principais do documento: Segurança, Confiabilidade e Auditabilidade. A Recuperabilidade entra com as provas, na Sprint 2.

**Valor validado:** um usuário cria a conta, confirma o e-mail, entra e mantém uma sessão segura, e cada uma dessas ações fica registrada na trilha de auditoria.

### Cálculo da fatia

| Sprint | RFs | Quantidade | % |
|---|---|---|---|
| **1** | RF01, RF02, RF03, RF06, RF11 (parcial), RF18, RF21 | **7 de 21** | **33%** |
| 2 | RF04, RF05, RF07–RF10, RF11 (restante), RF12–RF17, RF19, RF20 | 14 de 21 | 67% |

O RF11 é contado na Sprint 1 porque os dois e-mails exigidos pelos RFs da sprint (verificação e boas-vindas) são entregues nela. Os demais templates ficam para a Sprint 2 (#33). A meta da disciplina é de pelo menos 30%.

### Legenda de status

| Status | Significado |
|---|---|
| `planejado` | Nenhum código do requisito na `main` |
| `em andamento` | Parte entregue na `main` (por exemplo, a tela pronta e o serviço ainda não) |
| `implementado` | Critério de verificação atendido na `main`, de ponta a ponta |

## 2. Requisitos funcionais

| ID | Requisito | Serviço | ADR | Doc. | Sprint | Status | Issues |
|---|---|---|---|---|---|---|---|
| RF01 | Cadastro de conta (nome, e-mail, senha) | Autenticação | [002](adr/0002-seguranca.md) | 4.2.1 | 1 | em andamento | #7, #13 |
| RF02 | Verificação de e-mail por código | Autenticação + Notificação | [007](adr/0007-verificacao-do-email-do-usuario.md) | 4.2.1 | 1 | em andamento | #8, #13 |
| RF03 | Login/logout com sessão JWT | Autenticação | [002](adr/0002-seguranca.md), [017](adr/0017-aplicacao-web-nextjs-com-bff.md) | 4.2.1 | 1 | em andamento | #9, #14 |
| RF04 | MFA obrigatório (TOTP / e-mail) | Autenticação | [009](adr/0009-verificacao-em-multiplas-etapas.md) | 4.2.1 | 2 | planejado | #18, #20 |
| RF05 | Recuperação de senha por link via e-mail | Autenticação + Notificação | [008](adr/0008-recuperacao-da-conta-por-link-via-email.md) | 4.2.1 | 2 | planejado | #19, #20 |
| RF06 | Perfil do usuário (ver/editar) | Autenticação | — | 4.2.1 | 1 | em andamento | #10, #14 |
| RF07 | Catálogo de pacotes de créditos | Pagamento | — | 4.2.2 | 2 | planejado | #21, #25 |
| RF08 | Compra via PIX (checkout transparente) | Pagamento | [013](adr/0013-pagamento-por-servico-externo.md) | 4.2.2 | 2 | planejado | #22, #25 |
| RF09 | Confirmação de pagamento e faturamento | Pagamento | [013](adr/0013-pagamento-por-servico-externo.md) | 4.2.2 | 2 | planejado | #23 |
| RF10 | Saldo e extrato de créditos | Pagamento | — | 4.2.2 | 2 | planejado | #24, #25 |
| RF11 | Notificações transacionais por e-mail | Notificação | [016](adr/0016-comunicacao-interna-http-fire-and-forget.md) | 4.2.3 | 1 (verificação, boas-vindas) / 2 (demais) | em andamento | #6, #33 |
| RF12 | Registro de captura (prova) com débito de crédito | Captura | [005](adr/0005-arquitetura-baseada-em-servicos.md) | 4.2.4 | 2 | planejado | #29, #32 |
| RF13 | Captura de tela de URL | Captura | [005](adr/0005-arquitetura-baseada-em-servicos.md) | 4.2.4 | 2 | planejado | #30, #32 |
| RF14 | Gravação de vídeo de navegação | Captura | [005](adr/0005-arquitetura-baseada-em-servicos.md) | 4.2.4 | 2 | planejado | #31, #32 |
| RF15 | Armazenamento imutável com hash SHA-256 | Armazenamento | [010](adr/0010-divisao-dos-bancos-de-dados.md), [011](adr/0011-integridade-das-provas-por-hash.md), [019](adr/0019-minio-como-object-storage.md) | 4.2.5 | 2 | planejado | #26, #27 |
| RF16 | Consulta, listagem e download de provas | Armazenamento | [010](adr/0010-divisao-dos-bancos-de-dados.md) | 4.2.5 | 2 | planejado | #28, #32 |
| RF17 | Verificação de integridade pelo usuário | Armazenamento | [011](adr/0011-integridade-das-provas-por-hash.md) | 4.2.5 | 2 | planejado | #28, #32 |
| RF18 | Registro de auditoria imutável de ações | Monitoramento | [001](adr/0001-auditabilidade-registros-de-auditoria.md), [012](adr/0012-geracao-de-logs-estruturados.md), [015](adr/0015-log-storage-em-database-mysql-separada.md) | 4.2.6 | 1 | em andamento | #4, #5 |
| RF19 | Limpeza/retenção de logs operacionais | Monitoramento | [012](adr/0012-geracao-de-logs-estruturados.md) | 4.2.6 | 2 | planejado | #35 |
| RF20 | Consulta da trilha de auditoria | Monitoramento | [001](adr/0001-auditabilidade-registros-de-auditoria.md) | 4.2.6 | 2 | planejado | #34, #36 |
| RF21 | API Gateway único com autenticação centralizada | Gateway | [005](adr/0005-arquitetura-baseada-em-servicos.md), [018](adr/0018-api-gateway-como-servico-fastapi.md) | 4 (item 7), 4.1 | 1 | em andamento | #11 |

A coluna **Doc.** indica a seção do documento "Estruturação do Veridit" que descreve o módulo.

## 3. Detalhamento dos RFs da Sprint 1

Os caminhos de API são os do gateway (`/api/...`), que é o que a web e o avaliador usam. Internamente, o gateway repassa para o serviço sem o prefixo `/api` (#11).

### RF01 – Cadastro de conta

- **Descrição:** a pessoa cria uma conta com nome, e-mail e senha.
- **Regras de negócio:**
  - Senha com no mínimo 10 caracteres, pelo menos 1 letra e 1 número. Armazenada com Argon2id, nunca em texto puro nem em log.
  - E-mail normalizado (sem espaços, minúsculo) e único.
  - A conta nasce `pending_verification` e não consegue entrar até verificar o e-mail (RF02).
  - O cadastro dispara o e-mail de verificação (RF11) e o evento de auditoria `auth.user.registered` (RF18).
- **Critério de verificação:**
  1. `POST /api/auth/register` com dados válidos → `201` com `status: "pending_verification"`.
  2. Repetir com o mesmo e-mail em maiúsculas → `409`.
  3. Senha `abc` → `422` com mensagem em PT-BR.
  4. Na tabela `users`, `password_hash` começa com `$argon2id$`.
  5. Na web, `/cadastro` mostra os erros por campo e, com sucesso, redireciona para `/verificar-email`.
- **Issues:** #7 (back-end), #13 (web).

### RF02 – Verificação de e-mail por código

- **Descrição:** a pessoa confirma o e-mail digitando o código de 6 dígitos recebido por e-mail.
- **Regras de negócio:**
  - Código numérico de 6 dígitos, válido por 15 minutos. Só o hash fica no banco.
  - No máximo 5 tentativas por código; depois disso, o código é invalidado.
  - O reenvio respeita um intervalo de 60 s e no máximo 5 por hora. Ele sempre responde `202`, para não revelar se o e-mail existe, e um código novo invalida os anteriores.
  - Ao confirmar, a conta passa a `active`, o e-mail de boas-vindas é enviado e o evento `auth.email.verified` é registrado.
- **Critério de verificação:**
  1. Código correto → `200` e conta `active`.
  2. Código errado → `400` com as tentativas restantes. Na 6.ª tentativa, mesmo com o código certo → `400` "Código expirado, solicite outro".
  3. Código com mais de 15 min → `400`.
  4. Dois reenvios em menos de 60 s → o segundo é recusado.
  5. Em dev, o e-mail aparece no Mailpit (`localhost:8025`).
  6. Na web, `/verificar-email` aceita colar o código e libera o reenvio após 60 s.
- **Issues:** #8 (back-end), #6 (envio), #13 (web).

### RF03 – Login e logout com sessão JWT

- **Descrição:** a pessoa entra com e-mail e senha e sai quando quiser. A sessão se renova sozinha enquanto o refresh token for válido.
- **Regras de negócio:**
  - E-mail inexistente e senha errada dão a mesma resposta (`401`), em tempo semelhante.
  - Conta não verificada → `403` com `email_not_verified`.
  - Access token JWT RS256 de 15 min. Refresh token de 7 dias, guardado como hash, **rotativo**: reusar um refresh revogado revoga todas as sessões do usuário.
  - Na web, os tokens ficam só em cookies `httpOnly` ([ADR-017](adr/0017-aplicacao-web-nextjs-com-bff.md)).
  - Rate limit de 5 tentativas de login por minuto (RNF01).
  - Eventos de auditoria: `login_succeeded`, `login_failed`, `logout`, `refresh_reuse_detected`.
- **Critério de verificação:**
  1. Credenciais válidas → `200` com `access_token`, `refresh_token` e `expires_in`.
  2. Senha errada → `401`; e-mail inexistente → `401` com a mesma mensagem.
  3. Conta não verificada → `403` `email_not_verified`, e a web redireciona para `/verificar-email`.
  4. 6.ª tentativa no mesmo minuto → `429` com `Retry-After`.
  5. Usar duas vezes o mesmo refresh token → a segunda chamada falha e o próximo acesso exige login.
  6. Na web, com o cookie `vrd_access` apagado, a navegação continua (renovação pelo `proxy.ts`). Após "Sair", abrir `/perfil` leva a `/entrar?next=/perfil`.
- **Issues:** #9 (back-end), #14 (web).

### RF06 – Perfil do usuário

- **Descrição:** a pessoa logada vê os próprios dados, edita o nome e troca a senha.
- **Regras de negócio:**
  - Só `name` é editável. `email` ou `status` enviados no corpo são ignorados (sem *mass assignment*).
  - A troca de senha exige a senha atual, aplica a mesma política do RF01 e encerra as outras sessões.
  - Eventos de auditoria: `auth.profile.updated` (só os nomes dos campos) e `auth.password.changed`.
- **Critério de verificação:**
  1. `GET /api/me` → `200` com `id`, `name`, `email`, `status`, `email_verified_at` e `created_at`.
  2. `PATCH /api/me` com `{"name": "X", "email": "outro@x"}` → o nome muda e o e-mail não.
  3. Senha atual errada → `400`.
  4. Depois de trocar a senha, um refresh token de outra sessão deixa de funcionar.
  5. Na web, `/perfil` mostra os dados, e salvar o nome atualiza a barra lateral.
- **Issues:** #10 (back-end), #14 (web).

### RF11 – Notificações por e-mail (parcial: verificação e boas-vindas)

- **Descrição:** serviço interno que envia e-mails a partir de *triggers* dos outros serviços (seção 4.2.3 do documento).
- **Regras de negócio:**
  - Só acessível pela rede interna, com token interno; sem rota no gateway.
  - Templates HTML e texto puro.
  - Até 3 tentativas com backoff exponencial.
  - Deduplicação por `idempotency_key`.
  - Cada envio é registrado no Monitoramento com o destinatário mascarado.
- **Critério de verificação:**
  1. `POST /internal/notifications` com `template=email_verification` → `202`, e o e-mail aparece no Mailpit.
  2. Template desconhecido → `422` com a lista dos válidos.
  3. Repetir a mesma `idempotency_key` → nenhum e-mail novo.
  4. `GET /api/notifications` no gateway → `404`.
- **Issues:** #6 (Sprint 1), #33 (demais templates, Sprint 2).

### RF18 – Registro de auditoria imutável

- **Descrição:** toda ação relevante gera um evento com ator, ação, IP, data e hora, gravado num armazenamento que ninguém pode editar ([ADR-001](adr/0001-auditabilidade-registros-de-auditoria.md)).
- **Regras de negócio:**
  - Eventos aceitos só pela rede interna (`POST /internal/events`, token interno).
  - Idempotentes por `event_id`.
  - `received_at` vem do relógio do servidor, `occurred_at` do emissor, ambos em UTC com microssegundos ([ADR-021](adr/0021-datas-utc-datetime6.md)).
  - Gravados em `veriditi_logs.audit_events` por um usuário MySQL sem `UPDATE`/`DELETE` ([ADR-015](adr/0015-log-storage-em-database-mysql-separada.md)).
  - Na Sprint 1 o transporte é HTTP "fire-and-forget" ([ADR-016](adr/0016-comunicacao-interna-http-fire-and-forget.md)).
- **Critério de verificação:**
  1. Depois de um login, existe uma linha em `audit_events` com `actor_id`, `actor_ip` e `occurred_at`.
  2. Reenviar o mesmo `event_id` → `202` e nenhuma linha nova.
  3. `UPDATE audit_events ...` com o usuário `veriditi_logs_writer` → erro de permissão.
  4. `make db-test-contract` passa.
- **Issues:** #4 (cliente na lib comum), #5 (serviço). A modelagem do #41 já está pronta (`docs/banco-de-dados.md`, seção 5.5).

### RF21 – API Gateway único

- **Descrição:** ponto de entrada único da API. A web conhece só o gateway (seção 4.1 do documento; [ADR-018](adr/0018-api-gateway-como-servico-fastapi.md)).
- **Regras de negócio:**
  - Rotas públicas e protegidas declaradas numa tabela.
  - Valida o JWT (assinatura, `exp`, `iss`, `aud`) antes de repassar.
  - Injeta `X-User-Id`, `X-User-Email`, `X-Session-Id` (claim `sid`), `X-Request-ID`, `X-Forwarded-For` e o token interno, removendo esses cabeçalhos se vierem do cliente.
  - Notificação e Monitoramento não têm rota.
  - Timeout de upstream de 5 s.
  - Rate limit de login, cadastro e reenvio do código.
- **Estado (#11):** gateway implementado em `services/gateway` (tabela de rotas, JWT RS256, rate limit, anti-spoofing, 502/503/504, `/health/ready` agregado), com testes de API para cada critério abaixo. O fluxo de ponta a ponta depende do auth com os endpoints (#7–#10).
- **Critério de verificação:**
  1. `GET /api/me` sem token → `401`; com um token adulterado → `401`.
  2. `X-User-Id` forjado pelo cliente é ignorado.
  3. `/api/notifications` e `/api/events` → `404`.
  4. Com o serviço de autenticação parado → `503` com mensagem, e o gateway continua de pé.
  5. `GET /health/ready` agrega o estado dos upstreams.
  6. Só o gateway (`:8080`) e a web (`:3000`) expõem porta de aplicação no host.
- **Issues:** #11 (gateway), #3 (esqueleto e compose).

## 4. RFs da Sprint 2: critério de verificação

| ID | Critério de verificação objetivo | Issues |
|---|---|---|
| RF04 | Primeiro login após verificar o e-mail exige configurar o TOTP; logins seguintes retornam `mfa_required: true` sem tokens até `POST /api/auth/mfa/verify` com código válido | #18, #20 |
| RF05 | `POST /api/auth/password/forgot` sempre `202`; o link do e-mail redefine a senha uma única vez em até 30 min e encerra todas as sessões | #19, #20 |
| RF07 | `GET /api/packages` (sem login) lista os pacotes ativos ordenados por preço, com valores em centavos | #21, #25 |
| RF08 | `POST /api/orders` com `Idempotency-Key` devolve QR Code e copia-e-cola PIX; repetir a chamada devolve o mesmo pedido | #22, #25 |
| RF09 | Webhook com assinatura inválida → `401`; o mesmo evento entregue N vezes credita uma única vez | #23 |
| RF10 | `GET /api/credits/balance` reflete compras e capturas; o extrato lista cada movimento; débito sem saldo → `402` | #24, #25 |
| RF11 (rest.) | Cada template novo renderiza em teste de snapshot e chega ao Mailpit | #33 |
| RF12 | `POST /api/captures` debita créditos e retorna `202`; o status evolui até `completed`; falha definitiva estorna os créditos | #29, #32 |
| RF13 | Captura `screenshot` gera PNG de página inteira com manifesto (URL final, data UTC, certificado TLS) | #30 |
| RF14 | Captura `video` gera WebM com URL e relógio UTC visíveis, entre 10 e 60 s | #31 |
| RF15 | O SHA-256 gravado é igual ao `sha256sum` do arquivo; apagar o objeto antes da retenção falha (Object Lock) | #26, #27 |
| RF16 | `GET /api/evidences` lista só as provas do usuário logado (teste de IDOR); o download entrega o arquivo e o manifesto | #28, #32 |
| RF17 | A verificação pública aceita um arquivo ou hash e informa se corresponde a uma prova registrada | #28, #32 |
| RF19 | O job de limpeza remove `operational_logs` mais antigos que a retenção, sem tocar em `audit_events` | #35 |
| RF20 | `GET /api/audit/me` lista os eventos do usuário; `verify-chain` aponta o primeiro evento adulterado | #34, #36 |

## 5. Requisitos não funcionais

| ID | Requisito | Característica | ADR | Sprint | Status | Issues |
|---|---|---|---|---|---|---|
| RNF01 | Senhas com Argon2id, JWT assinado, rate limit no login, serviços internos não expostos | Segurança | [002](adr/0002-seguranca.md), [017](adr/0017-aplicacao-web-nextjs-com-bff.md), [018](adr/0018-api-gateway-como-servico-fastapi.md), [020](adr/0020-banco-central-compartilhado-com-posse-por-servico.md) | 1 | em andamento | #3, #7, #9, #11, #41 |
| RNF02 | Falha de um serviço não derruba os demais (timeouts, isolamento) | Confiabilidade / Tolerância a falhas | [003](adr/0003-confiabilidade.md), [016](adr/0016-comunicacao-interna-http-fire-and-forget.md) | 1 e 2 | em andamento | #11, #12, #37 |
| RNF03 | Toda ação relevante gera evento de auditoria com ator, IP e data/hora | Auditabilidade | [001](adr/0001-auditabilidade-registros-de-auditoria.md), [015](adr/0015-log-storage-em-database-mysql-separada.md), [021](adr/0021-datas-utc-datetime6.md) | 1 | em andamento | #4, #5 |
| RNF04 | Provas em object storage separado do banco relacional; backups | Recuperabilidade | [004](adr/0004-recuperabilidade.md), [010](adr/0010-divisao-dos-bancos-de-dados.md), [019](adr/0019-minio-como-object-storage.md) | 2 | planejado | #26, #37 |
| RNF05 | Cobertura de testes ≥ 70% por serviço; CI obrigatório | Testabilidade | [023](adr/0023-migrations-por-servico-e-testes-com-mysql.md) | 1 e 2 | em andamento | #15, #38 |
| RNF06 | Web responsiva (≥ 360 px); sistema sobe com um comando (Docker) | Portabilidade | [006](adr/0006-aplicacao-web.md) | 1 | em andamento | #3, #12 |
| RNF07 | Fluxos com mensagens claras em PT-BR, acessibilidade básica | Usabilidade | [017](adr/0017-aplicacao-web-nextjs-com-bff.md) | 1 | em andamento | #12, #13, #14 |
| RNF08 | p95 < 300 ms nas rotas síncronas (exceto captura) | Desempenho | — | 2 | planejado | #38 |

### Critério de verificação dos RNFs

| ID | Como verificar | Situação na `main` |
|---|---|---|
| RNF01 | `password_hash` começa com `$argon2id$`; token adulterado → `401`; 6.º login no minuto → `429`; `docker compose ps` mostra porta publicada só no gateway, na web, no Mailpit e no MySQL (dev); no DevTools, os cookies `vrd_*` são `HttpOnly`; `make db-test-contract` prova o privilégio mínimo | Cookies `httpOnly` e anti *open redirect* na web; usuários MySQL por serviço e teste de contrato prontos; validação do JWT, rate limit (login, cadastro e reenvio) e porta do gateway só no loopback prontos no gateway (#11); Argon2id e emissão do JWT dependem de #7 e #9 |
| RNF02 | Com o serviço de autenticação parado, a web mostra "Serviço indisponível" e continua navegável, e o gateway responde `503` | Timeout de 8 s e mensagem de indisponibilidade na web; `/health/live` e `/health/ready` na lib comum; gateway responde `503`/`504` e continua de pé com o auth parado (#11) |
| RNF03 | Toda ação dos RFs da Sprint 1 aparece em `audit_events` com `actor_id`, `actor_ip` e `occurred_at` em UTC | A web repassa `X-Forwarded-For` e `User-Agent`; tabela modelada e database criada; serviço pendente (#5) |
| RNF04 | Objeto em bucket com Object Lock; restaurar o backup do dia em outra máquina | Sprint 2 |
| RNF05 | CI verde em todo PR; `pytest --cov` ≥ 70% em cada serviço | CI com lint, tipos, testes e build (jobs `backend`, `web`, `docker`); testes na lib comum e no template; meta de cobertura e matriz por serviço em #15 |
| RNF06 | Telas utilizáveis a 360 px; `make up` em máquina limpa deixa todos os containers `healthy` e o fluxo do RF01 funcionando | Telas responsivas prontas; o `docker-compose.yml` ainda não tem o serviço `gateway` (#3/#11) |
| RNF07 | Todas as mensagens de erro em PT-BR; todos os fluxos percorríveis só com teclado; erros ligados ao campo por `aria-describedby` | Atendido nas telas da Sprint 1 (`lib/errors.ts`, `FormField`); revalidar a cada tela nova |
| RNF08 | Teste de carga: p95 < 300 ms em `/api/auth/login` e `/api/me` | Sprint 2 (#38) |

### Restrições técnicas e padrões

| Tema | Padrão adotado | Referência |
|---|---|---|
| Arquitetura | Baseada em serviços; só o gateway e a web são públicos; Notificação e Monitoramento são internos | [ADR-005](adr/0005-arquitetura-baseada-em-servicos.md) |
| Monorepo | `apps/web` (Next.js), `services/<serviço>` (FastAPI), `libs/python/common` (só infraestrutura), `packages/` (futuro); uv workspace e npm workspaces | `README.md` |
| Front-end | Next.js 16 (App Router, Server Actions), React 19, TypeScript, Tailwind 4, zod 4; padrão BFF | [ADR-017](adr/0017-aplicacao-web-nextjs-com-bff.md) |
| Back-end | Python ≥ 3.12, FastAPI, SQLAlchemy 2 async, Alembic | [ADR-018](adr/0018-api-gateway-como-servico-fastapi.md), [ADR-023](adr/0023-migrations-por-servico-e-testes-com-mysql.md) |
| Dados | MySQL 8.4 (Banco Central + `veriditi_logs`), posse por serviço, datas em UTC; MinIO na Sprint 2 | [ADR-014](adr/0014-mysql-como-banco-de-dados-central.md), [015](adr/0015-log-storage-em-database-mysql-separada.md), [020](adr/0020-banco-central-compartilhado-com-posse-por-servico.md)–[022](adr/0022-convencoes-do-modelo-fisico.md), [`banco-de-dados.md`](banco-de-dados.md) |
| Qualidade | ruff, mypy, pytest; ESLint e `tsc`; GitHub Actions | `.github/workflows/ci.yml` |
| Entrega | Docker Compose; imagens publicadas pelo CI e implantadas numa VM com Caddy (TLS) | #17 |

## 6. Escopo

### Dentro da Sprint 1

| Frente | Entregas | Issues |
|---|---|---|
| Documentação | Este documento; ADRs e desvios; modelagem do banco; README de execução e documento SOLID | #1, #2, #41, #16 |
| Infraestrutura | Monorepo com os 4 serviços da sprint; lib comum com logging, `X-Request-ID` e clientes de Auditoria/Notificação | #3, #4 |
| Back-end | Monitoramento (RF18), Notificação (RF11 parcial), Autenticação (RF01, RF02, RF03, RF06), Gateway (RF21) | #5–#11 |
| Web | Fundação BFF; telas de cadastro, verificação, login, painel e perfil | #12, #13, #14 |
| Qualidade e entrega | Testes por serviço com cobertura ≥ 70%; sistema rodando publicamente | #15, #17 |

### Fora da Sprint 1 (reservado para a Sprint 2)

- MFA obrigatório e recuperação de senha (RF04, RF05).
- Todo o serviço de Pagamento: pacotes, PIX, webhook, carteira (RF07–RF10). O painel mostra o card "Créditos" como "em breve".
- Captura de tela e de vídeo, e a fila de processamento (RF12–RF14). O botão "Iniciar uma gravação" fica desabilitado.
- Armazenamento das provas no MinIO, hash e verificação pública (RF15–RF17).
- Templates de e-mail além de verificação e boas-vindas (RF11 restante).
- Limpeza de logs e consulta da trilha de auditoria (RF19, RF20).
- Outbox, Redis Streams, retentativas, DLQ e backups (#37); testes E2E e de carga (#38).

### Fora do escopo do projeto nesta versão

Nenhum RF fora da lista RF01–RF21. Uma funcionalidade nova entra primeiro aqui e numa issue, com sprint definida.

## 7. Rastreabilidade (Sprint 1)

| RF | Issues | Web (`apps/web/src`) | Back-end | Banco |
|---|---|---|---|---|
| RF01 | #7, #13 (PR #45) | `app/(public)/cadastro/`, `components/auth/password-strength.tsx`, `lib/validation/auth.ts` | `services/auth` (a criar, #3/#7) | `users` (seção 5.1) |
| RF02 | #8, #6, #13 (PR #45) | `app/(public)/verificar-email/`, `components/ui/otp-input.tsx` | `services/auth`, `services/notification` (a criar) | `email_verification_codes` (5.2) |
| RF03 | #9, #14 (PR #46) | `app/(public)/entrar/`, `app/(app)/actions.ts`, `lib/gateway.ts`, `lib/tokens.ts`, `lib/session.ts`, `proxy.ts`, `app/sessao/expirada/` | `services/auth` (a criar) | `refresh_tokens` (5.3) |
| RF06 | #10, #14 (PR #46) | `app/(app)/perfil/`, `lib/user.ts` | `services/auth` (a criar) | `users` (5.1) |
| RF11 | #6 | — | `services/notification` | `notifications_sent` (5.4) |
| RF18 | #4, #5, #41 (PR #49) | `lib/gateway.ts` (repassa IP e User-Agent) | `services/monitoring` (a criar); `docker/mysql/init/` | `veriditi_logs.audit_events` (5.5) |
| RF21 | #11, #3 | `lib/config.ts`, `lib/gateway.ts`, `app/api/health/route.ts`; mock em `apps/web/mock/gateway.mjs` (PR #44/#47) | `services/gateway` | — |

As seções de banco referem-se a [`banco-de-dados.md`](banco-de-dados.md). Hoje, o único serviço Python no repositório é o template `services/users`, que vira `services/auth` no #3.

## 8. Como manter este documento

- **No fim de cada sprint:** atualizar as colunas **Status** das seções 2 e 5 e a coluna "Situação na `main`" da seção 5, e trocar a data no topo.
- **Um RF só passa a `implementado`** quando todos os itens do seu critério de verificação funcionam na `main`, de ponta a ponta (web + gateway + serviço).
- **Mudanças de escopo** (RF novo, RF trocado de sprint) entram aqui no mesmo PR que altera a issue, e mudam o cálculo da seção 1.
