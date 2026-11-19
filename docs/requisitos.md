# Requisitos e escopo da Sprint 1 (30%)

> **Fontes:** documento "Estruturação do Veridit" (Trabalho II de MATA62), transcrito nas [ADRs 001–013](adr/README.md), que dá a numeração RF01–RF21; e o **Documento de Requisitos** v01.00 (REQ01–REQ15, Apêndice A e decisões D1/D2), mapeado para os RFs na [seção 9](#9-rastreabilidade-com-o-documento-de-requisitos).
> **Planejamento:** épico #40; milestones *Sprint 1 – 30% dos requisitos* e *Sprint 2 – 70% restantes*.
> **Status conferido em:** 2026-11-19, contra o código da `main` (`918a4e8`) e o stack rodando com `make up`. Atualize as colunas de status no fim da sprint (ver [seção 8](#8-como-manter-este-documento)).

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
| **1** | RF01, RF02, RF03, RF05, RF06, RF11 (parcial), RF18, RF21, RF22 | **9 de 22** | **40,9%** |
| 2 | RF04, RF07–RF10, RF11 (restante), RF12–RF17, RF19, RF20 | 13 de 22 | 59,1% |

O RF11 é contado na Sprint 1 porque os dois e-mails exigidos pelos RFs da sprint (verificação e boas-vindas) são entregues nela. Os demais templates ficam para a Sprint 2 (#33). A meta da disciplina é de pelo menos 30%.

Em 2026-11-18 a Sprint 1 foi ampliada: o RF05 (recuperação de senha, #19) e o RF22 (tipos de conta, #60, criado nessa data) entraram nela. Os milestones mantêm o nome original.

Pela numeração do Documento de Requisitos, a Sprint 1 entrega **REQ01, REQ02, REQ03 e REQ04: 4 de 15 (26,7%)**. A diferença para os 40,9% vem da granularidade: o Documento de Requisitos agrupa pagamento e captura em REQs grandes, enquanto a "Estruturação do Veridit" separa identidade, gateway, notificação e auditoria em RFs próprios. O mapeamento completo está na [seção 9](#9-rastreabilidade-com-o-documento-de-requisitos).

### Legenda de status

| Status | Significado |
|---|---|
| `planejado` | Nenhum código do requisito na `main` |
| `em andamento` | Parte entregue na `main` (por exemplo, a tela pronta e o serviço ainda não) |
| `implementado` | Critério de verificação atendido na `main`, de ponta a ponta |

### Conferência de 2026-11-19

Os critérios que não dependem da tela foram conferidos contra o stack rodando: 27 checagens pela API do gateway (cadastro, `409`/`422`, verificação, reenvio, login, `401` uniforme, `429` com `Retry-After`, reuso de refresh, `/me`, *mass assignment*, `401` de token adulterado, `X-User-Id` forjado, rotas internas `404`, `/health/ready`, `forgot` `202` e renovação da sessão pelo `proxy.ts`), mais os eventos em `audit_events` com `actor_id`, `actor_ip` e `occurred_at`, o `UPDATE` negado ao `veriditi_logs_writer`, o `$argon2id$`, o CPF cifrado (`cpf_hmac` de 64 caracteres, sem o CPF em claro no banco, nos logs ou na auditoria), as portas publicadas só em `127.0.0.1` e os cookies `vrd_*` com `HttpOnly`. Os demais itens dos critérios são cobertos pelos testes automatizados (`make cov`, `make db-test`), que passam na `main`.

Os itens que só se conferem no navegador estão na #69. Até ela fechar, os RFs que têm critério de web ficam `em andamento`, com o back-end e o gateway já conferidos.

## 2. Requisitos funcionais

| ID | Requisito | Serviço | ADR | Doc. | Sprint | Status | Issues |
|---|---|---|---|---|---|---|---|
| RF01 | Cadastro de conta (nome, e-mail, senha; tipo, CPF e OAB no RF22) | Autenticação | [002](adr/0002-seguranca.md) | 4.2.1 | 1 | em andamento (falta a web, #69) | #7, #13 |
| RF02 | Verificação de e-mail por código | Autenticação + Notificação | [007](adr/0007-verificacao-do-email-do-usuario.md) | 4.2.1 | 1 | em andamento (falta a web, #69) | #8, #13 |
| RF03 | Login/logout com sessão JWT | Autenticação | [002](adr/0002-seguranca.md), [017](adr/0017-aplicacao-web-nextjs-com-bff.md) | 4.2.1 | 1 | em andamento (falta a web, #69) | #9, #14 |
| RF04 | MFA obrigatório (TOTP / e-mail) | Autenticação | [009](adr/0009-verificacao-em-multiplas-etapas.md) | 4.2.1 | 2 | planejado | #18, #20 |
| RF05 | Recuperação de senha por link via e-mail | Autenticação + Notificação | [008](adr/0008-recuperacao-da-conta-por-link-via-email.md) | 4.2.1 | 1 | em andamento (falta a web, #69) | #19, #20 |
| RF06 | Perfil do usuário (ver/editar; tipo, CPF mascarado e OAB no RF22) | Autenticação | — | 4.2.1 | 1 | em andamento (falta a web, #69) | #10, #14 |
| RF07 | Catálogo de pacotes de créditos | Pagamento | — | 4.2.2 | 2 | planejado | #21, #25 |
| RF08 | Compra via PIX (checkout transparente) | Pagamento | [013](adr/0013-pagamento-por-servico-externo.md) | 4.2.2 | 2 | planejado | #22, #25 |
| RF09 | Confirmação de pagamento e faturamento | Pagamento | [013](adr/0013-pagamento-por-servico-externo.md) | 4.2.2 | 2 | planejado | #23 |
| RF10 | Saldo e extrato de créditos | Pagamento | — | 4.2.2 | 2 | planejado | #24, #25 |
| RF11 | Notificações transacionais por e-mail | Notificação | [016](adr/0016-comunicacao-interna-http-fire-and-forget.md) | 4.2.3 | 1 (verificação, boas-vindas) / 2 (demais) | em andamento (parte da Sprint 1 implementada) | #6, #33 |
| RF12 | Registro de captura (prova) com débito de crédito | Captura | [005](adr/0005-arquitetura-baseada-em-servicos.md) | 4.2.4 | 2 | planejado | #29, #32 |
| RF13 | Captura de tela de URL | Captura | [005](adr/0005-arquitetura-baseada-em-servicos.md) | 4.2.4 | 2 | planejado | #30, #32 |
| RF14 | Gravação de vídeo de navegação | Captura | [005](adr/0005-arquitetura-baseada-em-servicos.md) | 4.2.4 | 2 | planejado | #31, #32 |
| RF15 | Armazenamento imutável com hash SHA-256 | Armazenamento | [010](adr/0010-divisao-dos-bancos-de-dados.md), [011](adr/0011-integridade-das-provas-por-hash.md), [019](adr/0019-minio-como-object-storage.md) | 4.2.5 | 2 | planejado | #26, #27 |
| RF16 | Consulta, listagem e download de provas | Armazenamento | [010](adr/0010-divisao-dos-bancos-de-dados.md) | 4.2.5 | 2 | planejado | #28, #32 |
| RF17 | Verificação de integridade pelo usuário | Armazenamento | [011](adr/0011-integridade-das-provas-por-hash.md) | 4.2.5 | 2 | planejado | #28, #32 |
| RF18 | Registro de auditoria imutável de ações | Monitoramento | [001](adr/0001-auditabilidade-registros-de-auditoria.md), [012](adr/0012-geracao-de-logs-estruturados.md), [015](adr/0015-log-storage-em-database-mysql-separada.md) | 4.2.6 | 1 | implementado | #4, #5 |
| RF19 | Limpeza/retenção de logs operacionais | Monitoramento | [012](adr/0012-geracao-de-logs-estruturados.md) | 4.2.6 | 2 | planejado | #35 |
| RF20 | Consulta da trilha de auditoria | Monitoramento | [001](adr/0001-auditabilidade-registros-de-auditoria.md) | 4.2.6 | 2 | planejado | #34, #36 |
| RF21 | API Gateway único com autenticação centralizada | Gateway | [005](adr/0005-arquitetura-baseada-em-servicos.md), [018](adr/0018-api-gateway-como-servico-fastapi.md) | 4 (item 7), 4.1 | 1 | implementado | #11 |
| RF22 | Tipos de conta: pessoa e advogado, com CPF e inscrição na OAB | Autenticação | [024](adr/0024-cifragem-do-cpf.md) | — | 1 | em andamento (falta a web, #69) | #60 |

A coluna **Doc.** indica a seção do documento "Estruturação do Veridit" que descreve o módulo. O RF22 não está no documento: veio do dono do produto, que precisa distinguir advogados das demais pessoas.

## 3. Detalhamento dos RFs da Sprint 1

Os caminhos de API são os do gateway (`/api/...`), que é o que a web e o avaliador usam. Internamente, o gateway repassa para o serviço sem o prefixo `/api` (#11).

### RF01 – Cadastro de conta

- **Descrição:** a pessoa cria uma conta com nome, e-mail e senha.
- **Regras de negócio:**
  - Senha com no mínimo 10 caracteres, pelo menos 1 letra e 1 número. Armazenada com Argon2id, nunca em texto puro nem em log.
  - E-mail normalizado (sem espaços, minúsculo) e único.
  - A conta nasce `pending_verification` e não consegue entrar até verificar o e-mail (RF02).
  - O cadastro dispara o e-mail de verificação (RF11) e o evento de auditoria `auth.user.registered` (RF18).
  - Desde o RF22, o cadastro também exige o tipo de conta e o CPF, e o advogado informa a OAB.
- **Critério de verificação:**
  1. `POST /api/auth/register` com dados válidos (incluindo `user_type` e `cpf`, RF22) → `201` com `status: "pending_verification"`.
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

### RF05 – Recuperação de senha por link via e-mail

- **Descrição:** quem esqueceu a senha recebe por e-mail um link de uso único para definir outra ([ADR-008](adr/0008-recuperacao-da-conta-por-link-via-email.md)).
- **Critério de verificação:** `POST /api/auth/password/forgot` sempre `202`; o link do e-mail redefine a senha uma única vez em até 30 min e encerra todas as sessões. Link malformado, expirado, usado ou substituído → `400 invalid_reset_token`; senha fraca → `422` sem gastar o link; 4.º pedido do mesmo e-mail na hora → `429`. Entregue no back-end (#19) e nas telas `/esqueci-senha` e `/redefinir-senha` (parte do #20); o MFA do #20 continua pendente.
- **Issues:** #19 (back-end), #20 (web, só a recuperação).

### RF06 – Perfil do usuário

- **Descrição:** a pessoa logada vê os próprios dados, edita o nome e troca a senha.
- **Regras de negócio:**
  - Só `name` é editável. `email`, `status`, `user_type`, `cpf` ou `oab` enviados no corpo são ignorados (sem *mass assignment*).
  - Desde o RF22, o perfil mostra o tipo de conta, o CPF mascarado e a OAB informada no cadastro.
  - A troca de senha exige a senha atual, aplica a mesma política do RF01 e encerra as outras sessões.
  - Eventos de auditoria: `auth.profile.updated` (só os nomes dos campos) e `auth.password.changed`.
- **Critério de verificação:**
  1. `GET /api/me` → `200` com `id`, `name`, `email`, `status`, `email_verified_at`, `created_at`, `user_type`, `cpf_masked` e `oab` (RF22).
  2. `PATCH /api/me` com `{"name": "X", "email": "outro@x"}` → o nome muda e o e-mail não.
  3. Senha atual errada → `400`.
  4. Depois de trocar a senha, um refresh token de outra sessão deixa de funcionar.
  5. Na web, `/perfil` mostra os dados, e salvar o nome atualiza a barra lateral.
- **Issues:** #10 (back-end), #14 (web).

### RF22 – Tipos de conta: pessoa e advogado

- **Descrição:** no cadastro, a pessoa escolhe o tipo de conta, pessoa (`common`) ou advogado (`lawyer`). Toda conta informa o CPF; a de advogado informa também a inscrição na OAB (número, UF da seccional e tipo).
- **Regras de negócio:**
  - CPF com ou sem máscara, validado pelos dígitos verificadores; 11 dígitos repetidos são recusados. Um CPF por conta.
  - O CPF fica cifrado (AES-256-GCM) com um índice HMAC-SHA256 para a unicidade ([ADR-024](adr/0024-cifragem-do-cpf.md)). Nunca aparece em claro no banco, nos logs, na auditoria, nas respostas nem nas mensagens de erro. Só o `/me` decifra, e devolve mascarado (`***.982.247-**`).
  - OAB: número de 1 a 6 dígitos (zeros à esquerda não contam), uma das 27 UFs e tipo principal, suplementar ou transitória. Uma conta por UF e número. Conta comum não informa OAB.
  - A OAB é conferida só pelo formato. Sem consulta ao CNA (#64), a interface não diz que a inscrição foi verificada.
  - Tipo, CPF e OAB não mudam pelo perfil.
  - O evento `auth.user.registered` leva só o `user_type`.
- **Critério de verificação:**
  1. `POST /api/auth/register` com `user_type: "common"` e CPF válido → `201` com `user_type`; advogado com `oab: {number, uf, kind}` → `201`.
  2. CPF já cadastrado, com ou sem máscara → `409 cpf_already_registered`; mesma UF e número de OAB → `409 oab_already_registered`.
  3. CPF inválido → `422` "CPF inválido."; conta comum com `oab` → `422` "Só advogados informam OAB."; advogado sem `oab` → `422` "Informe a inscrição na OAB.".
  4. `GET /api/me` mostra `user_type`, `cpf_masked` e `oab`; `PATCH /api/me` com `cpf` ou `user_type` não muda nada.
  5. Em `users`, `cpf_enc` é binário sem o CPF em claro e `cpf_hmac` tem 64 caracteres hex; o CPF não aparece nos logs nem em `audit_events`.
  6. Na web, `/cadastro` pede o tipo, aplica a máscara do CPF e mostra a OAB só para advogado; `/perfil` mostra o CPF mascarado.
- **Pendências (Sprint 2):** o `409` por campo permite descobrir se um CPF está cadastrado (#61); rotação das chaves (#62), com o backup delas no deploy (#17); consulta ao CNA e várias inscrições (#64).
- **Issues:** #60.

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
- **Estado (#11):** gateway implementado em `services/gateway` (tabela de rotas, JWT RS256, rate limit, anti-spoofing, 502/503/504, `/health/ready` agregado), com testes de API para cada critério abaixo. Com o auth pronto (#7–#10), o fluxo de ponta a ponta foi conferido em 2026-11-19.
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
| RNF01 | Senhas com Argon2id, JWT assinado, rate limit no login, serviços internos não expostos | Segurança | [002](adr/0002-seguranca.md), [017](adr/0017-aplicacao-web-nextjs-com-bff.md), [018](adr/0018-api-gateway-como-servico-fastapi.md), [020](adr/0020-banco-central-compartilhado-com-posse-por-servico.md) | 1 | implementado | #3, #7, #9, #11, #41 |
| RNF02 | Falha de um serviço não derruba os demais (timeouts, isolamento) | Confiabilidade / Tolerância a falhas | [003](adr/0003-confiabilidade.md), [016](adr/0016-comunicacao-interna-http-fire-and-forget.md) | 1 e 2 | em andamento (parte da Sprint 1 implementada; falta a web, #69) | #11, #12, #37 |
| RNF03 | Toda ação relevante gera evento de auditoria com ator, IP e data/hora | Auditabilidade | [001](adr/0001-auditabilidade-registros-de-auditoria.md), [015](adr/0015-log-storage-em-database-mysql-separada.md), [021](adr/0021-datas-utc-datetime6.md) | 1 | implementado | #4, #5 |
| RNF04 | Provas em object storage separado do banco relacional; backups | Recuperabilidade | [004](adr/0004-recuperabilidade.md), [010](adr/0010-divisao-dos-bancos-de-dados.md), [019](adr/0019-minio-como-object-storage.md) | 2 | planejado | #26, #37 |
| RNF05 | Cobertura de testes ≥ 70% por serviço; CI obrigatório | Testabilidade | [023](adr/0023-migrations-por-servico-e-testes-com-mysql.md) | 1 e 2 | em andamento (parte da Sprint 1 implementada) | #15, #38 |
| RNF06 | Web responsiva (≥ 360 px); sistema sobe com um comando (Docker) | Portabilidade | [006](adr/0006-aplicacao-web.md) | 1 | em andamento (falta a web, #69) | #3, #12 |
| RNF07 | Fluxos com mensagens claras em PT-BR, acessibilidade básica | Usabilidade | [017](adr/0017-aplicacao-web-nextjs-com-bff.md) | 1 | em andamento (falta a web, #69) | #12, #13, #14 |
| RNF08 | p95 < 300 ms nas rotas síncronas (exceto captura) | Desempenho | — | 2 | planejado | #38 |

### Critério de verificação dos RNFs

| ID | Como verificar | Situação na `main` |
|---|---|---|
| RNF01 | `password_hash` começa com `$argon2id$`; token adulterado → `401`; 6.º login no minuto → `429`; `docker compose ps` mostra porta publicada só no gateway, na web, no Mailpit e no MySQL (dev); no DevTools, os cookies `vrd_*` são `HttpOnly`; `make db-test-contract` prova o privilégio mínimo | Conferido em 2026-11-19: `$argon2id$` no banco; token adulterado → `401`; 6.º login → `429` com `Retry-After`; portas publicadas só em `127.0.0.1` (gateway, web, Mailpit e MySQL de dev); cookies `vrd_*` com `HttpOnly`, `Secure` e `SameSite=lax`; `make db-test-contract` no CI. CPF cifrado desde o RF22 (ADR-024) |
| RNF02 | Com o serviço de autenticação parado, a web mostra "Serviço indisponível" e continua navegável, e o gateway responde `503` | Gateway responde `503`/`504` e continua de pé com o auth parado (testes do #11); `/health/live` e `/health/ready` em todos os serviços; timeout de 8 s e mensagem de indisponibilidade na web, a conferir no navegador (#69). Outbox e retentativas na Sprint 2 (#37) |
| RNF03 | Toda ação dos RFs da Sprint 1 aparece em `audit_events` com `actor_id`, `actor_ip` e `occurred_at` em UTC | Conferido em 2026-11-19: cadastro, verificação, login (sucesso e falha), reuso de refresh e edição de perfil geram linhas em `audit_events` com `actor_id`, `actor_ip` e `occurred_at`; o `veriditi_logs_writer` não consegue `UPDATE` (erro 1142) |
| RNF04 | Objeto em bucket com Object Lock; restaurar o backup do dia em outra máquina | Sprint 2 |
| RNF05 | CI verde em todo PR; `pytest --cov` ≥ 70% em cada serviço | CI com `lint`, `tests` em matriz (auth, gateway, notification, monitoring e lib comum; `make cov` falha abaixo de 70%), `database` (MySQL real), `web` (com vitest) e `images`; contrato gateway × auth em `test_gateway_contract.py`. Cobertura em 2026-11-19: gateway 99,9%, auth 77,0%, notification 99,4%, monitoring 98,9%, lib comum 97,4%. E2E e carga na Sprint 2 (#38) |
| RNF06 | Telas utilizáveis a 360 px; `make up` em máquina limpa deixa todos os containers `healthy` e o fluxo do RF01 funcionando | `make reset` + `make up` em 2026-11-19 deixou todos os containers `healthy`, com o gateway no compose, e o fluxo do RF01 funcionando. Quem já tinha `.env` precisa de `make keys` para as chaves do CPF (o `make install` já faz isso). Telas a 360 px a conferir (#69) |
| RNF07 | Todas as mensagens de erro em PT-BR; todos os fluxos percorríveis só com teclado; erros ligados ao campo por `aria-describedby` | Mensagens em PT-BR conferidas pela API (`409`, `422`, `400`, `403`); `FormField` liga o erro ao campo por `aria-describedby`. Teclado e leitor de tela a conferir depois do RF22 (#69) |
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
| Documentação | Este documento e o fechamento da sprint; ADRs e desvios; modelagem do banco; README de execução e documento SOLID | #1, #67, #2, #41, #16 |
| Infraestrutura | Monorepo com os 4 serviços da sprint; lib comum com logging, `X-Request-ID` e clientes de Auditoria/Notificação | #3, #4 |
| Back-end | Monitoramento (RF18), Notificação (RF11 parcial), Autenticação (RF01, RF02, RF03, RF05, RF06, RF22), Gateway (RF21) | #5–#11, #19, #60 |
| Web | Fundação BFF; telas de cadastro (com tipo de conta), verificação, login, painel, perfil e recuperação de senha | #12, #13, #14, #20, #60 |
| Qualidade e entrega | Testes por serviço com cobertura ≥ 70%; conferência na web; sistema rodando publicamente | #15, #69, #17 |

### Fora da Sprint 1 (reservado para a Sprint 2)

- MFA obrigatório (RF04).
- Melhorias do RF22 e do gateway abertas durante a Sprint 1: anti-enumeração no cadastro (#61), rotação das chaves do CPF (#62), rate limit em Redis (#63) e verificação da OAB no CNA (#64).
- Alinhamento das issues da Sprint 2 ao Documento de Requisitos: campos do Apêndice A, pacotes da D2, REQ06 e relatório do REQ14 (#70).
- Todo o serviço de Pagamento: pacotes, PIX, webhook, carteira (RF07–RF10). O painel mostra o card "Créditos" como "em breve".
- Captura de tela e de vídeo, e a fila de processamento (RF12–RF14). O botão "Iniciar uma gravação" fica desabilitado.
- Armazenamento das provas no MinIO, hash e verificação pública (RF15–RF17).
- Templates de e-mail além de verificação e boas-vindas (RF11 restante).
- Limpeza de logs e consulta da trilha de auditoria (RF19, RF20).
- Outbox, Redis Streams, retentativas, DLQ e backups (#37); testes E2E e de carga (#38).

### Fora do escopo do projeto nesta versão

Nenhum RF fora da lista RF01–RF22. Uma funcionalidade nova entra primeiro aqui e numa issue, com sprint definida.

## 7. Rastreabilidade (Sprint 1)

| RF | Issues | Web (`apps/web/src`) | Back-end | Banco |
|---|---|---|---|---|
| RF01 | #7, #13 (PRs #45, #54) | `app/(public)/cadastro/`, `components/auth/password-strength.tsx`, `lib/validation/auth.ts` | `services/auth` (`use_cases/register_user.py`) | `users` (seção 5.1) |
| RF02 | #8, #6, #13 (PRs #45, #54, #56) | `app/(public)/verificar-email/`, `components/ui/otp-input.tsx` | `services/auth` (`use_cases/verify_email.py`), `services/notification` | `email_verification_codes` (5.2) |
| RF03 | #9, #14 (PRs #46, #54) | `app/(public)/entrar/`, `app/(app)/actions.ts`, `lib/gateway.ts`, `lib/tokens.ts`, `lib/session.ts`, `proxy.ts`, `app/sessao/expirada/` | `services/auth` (`use_cases/authenticate_user.py`) | `refresh_tokens` (5.3) |
| RF06 | #10, #14 (PRs #46, #54) | `app/(app)/perfil/`, `lib/user.ts` | `services/auth` (`use_cases/profile.py`) | `users` (5.1) |
| RF11 | #6 (PR #56) | — | `services/notification` | `notifications_sent` (5.4) |
| RF18 | #4, #5, #41 (PRs #49, #53, #55) | `lib/gateway.ts` (repassa IP e User-Agent) | `libs/python/common` (`audit.py`), `services/monitoring`, `docker/mysql/init/` | `veriditi_logs.audit_events` (5.5) |
| RF05 | #19, #20 (só a recuperação; PR #65 e commit `918a4e8`) | `app/(public)/esqueci-senha/`, `app/(public)/redefinir-senha/`, link em `app/(public)/entrar/login-form.tsx`, headers em `next.config.ts` | `services/auth` (`use_cases/password_reset.py`), `services/notification` (`password_reset`, `password_changed`), `services/gateway` (rotas e limites) | `password_reset_tokens` (5.6), `refresh_tokens.revoke_reason` (5.3) |
| RF21 | #11, #3 (PRs #44, #47, #52, #57) | `lib/config.ts`, `lib/gateway.ts`, `app/api/health/route.ts`; mock em `apps/web/mock/gateway.mjs` | `services/gateway` | — |
| RF22 | #60 (PRs #66, #68) | `app/(public)/cadastro/`, `app/(app)/perfil/`, `lib/validation/cpf.ts`, `lib/validation/oab.ts` | `services/auth` (`domain/cpf.py`, `domain/oab.py`, `adapters/cpf_protector.py`) | `users` (5.1: `user_type`, `cpf_enc`, `cpf_hmac`, `oab_*`) |

As seções de banco referem-se a [`banco-de-dados.md`](banco-de-dados.md). O serviço Python de identidade e autenticação encontra-se em `services/auth`, estruturado com princípios SOLID documentados em [`solid.md`](solid.md) e transparência de IA em [`uso-de-ia.md`](uso-de-ia.md).

## 8. Como manter este documento

- **No fim de cada sprint:** atualizar as colunas **Status** das seções 2 e 5 e a coluna "Situação na `main`" da seção 5, e trocar a data no topo.
- **Um RF só passa a `implementado`** quando todos os itens do seu critério de verificação funcionam na `main`, de ponta a ponta (web + gateway + serviço).
- **Mudanças de escopo** (RF novo, RF trocado de sprint) entram aqui no mesmo PR que altera a issue, e mudam o cálculo da seção 1.
- **REQ novo ou alterado no Documento de Requisitos:** atualizar a tabela da seção 9 e, se não houver RF que o cubra, criar o RF e a issue.

## 9. Rastreabilidade com o Documento de Requisitos

O Documento de Requisitos (v01.00, REQ01–REQ15) não divide o trabalho em sprints. A tabela liga cada REQ aos RFs deste documento. Ele traz dois requisitos com o número 11; aqui eles aparecem como REQ11a (concluir a captura de tela) e REQ11b (confirmar a captura por e-mail).

| REQ | Requisito (prioridade) | RF | Sprint | Situação | Observação |
|---|---|---|---|---|---|
| REQ01 | Cadastrar usuário (alta), com os campos do Apêndice A e a decisão D1 | RF01, RF22 | 1 | Back-end conferido; web na #69 | D1: advogado e usuário comum na primeira versão, com nome, e-mail, senha e CPF, mais a OAB para advogado. Empresas ficam fora desta versão, como a D1 prevê |
| REQ02 | Recuperar senha (média) | RF05 | 1 | Back-end conferido; web na #69 | Antecipado da Sprint 2 em 2026-11-18 |
| REQ03 | Logar no sistema (alta) | RF03 (+ RF02, RF21) | 1 | Back-end conferido; web na #69 | O login exige o e-mail verificado (RF02, ADR-007), regra que vem da "Estruturação do Veridit" |
| REQ04 | Sair do sistema (alta) | RF03 | 1 | Back-end conferido; web na #69 | `POST /api/auth/logout` e "Sair" no menu |
| REQ05 | Comprar créditos (alta), com a decisão D2 | RF07, RF08 | 2 | planejado | Pacotes da D2 (básico, médio e premium) e dados de faturamento do Apêndice A ainda não estão nas issues (#70) |
| REQ06 | Efetuar pagamento de créditos (alta) | RF08, RF09 | 2 | planejado | Mercado Pago ou "pela plataforma do Veridit" com QR Code ou código PIX (ADR-013); definir na #70 |
| REQ07 | Confirmar pagamento por e-mail (alta) | RF09, RF11 | 2 | planejado | Template na #33 |
| REQ08 | Iniciar registro de conteúdo (alta) | RF12, RF13, RF14 | 2 | planejado | Apêndice A: endereço do site e **título do registro** (#70) |
| REQ09 | Concluir gravação de conteúdo (alta) | RF14 | 2 | planejado | |
| REQ10 | Confirmar gravação por e-mail (alta) | RF11 | 2 | planejado | Template na #33 |
| REQ11a | Concluir captura de tela (alta) | RF13 | 2 | planejado | |
| REQ11b | Confirmar captura de tela por e-mail (alta) | RF11 | 2 | planejado | Template na #33 |
| REQ12 | Listar registros realizados (alta) | RF16 | 2 | planejado | Apêndice A: título, início, fim, detalhes e status |
| REQ13 | Visualizar detalhes do registro (alta) | RF16 | 2 | planejado | Apêndice A: id, título, início, fim, tipos de dados, número de imagens e vídeos, usuário responsável |
| REQ14 | Gerar relatório do registro (alta) | RF16 (a confirmar) | 2 | planejado | **Sem issue que o cubra.** O relatório pede, entre outros, CPF do usuário, duração e nome e tamanho do arquivo; decidir na #70 se amplia o RF16 ou vira RF novo |
| REQ15 | Gerar arquivo zip do registro (alta) | RF16 | 2 | planejado | `GET /api/evidences/{id}/package` (#28) |
| Segurança | Acesso só por usuários cadastrados | RNF01, RF21 | 1 | implementado | O gateway exige JWT nas rotas protegidas e o `proxy.ts` protege `/painel` e `/perfil` |

RFs sem REQ correspondente, vindos da "Estruturação do Veridit": RF02 (verificação de e-mail), RF04 (MFA), RF06 (perfil), RF10 (saldo e extrato), RF15 e RF17 (integridade por hash), RF18 a RF20 (auditoria) e RF21 (gateway).
