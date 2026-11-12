# Architecture Decision Records (ADRs)

Decisões de arquitetura do Veriditi. As ADRs 001–013 são a transcrição do documento **"Estruturação do Veridit"** (Trabalho II de MATA62), escrito pela equipe arquiteta: Beatriz Marques dos Santos, Danielle Santos de Souza, Giovanna Ferrúcio Farani e Luiz Antony Duarte Ribeiro. As ADRs a partir da 014 registram desvios ou detalhamentos feitos durante a implementação.

Para criar uma ADR nova, copie o [modelo](0000-template.md) com o próximo número livre.

## Legenda de status

| Status | Significado |
|---|---|
| **Proposta** | Decisão em uso ou planejada, ainda **sem** o aceite registrado da equipe arquiteta |
| **Aceita** | Aprovada. Para ADRs de desvio, só com a tabela "Aceite da equipe arquiteta" preenchida (integrante, data e evidência) |
| **Substituída** | Trocada por outra ADR, indicada no campo Status |

Nenhuma ADR de desvio pode ser marcada como **Aceita** sem o registro do aceite.

## Índice

### Documento original (Trabalho II)

| ADR | Título | Status | Seção do documento |
|---|---|---|---|
| [001](0001-auditabilidade-registros-de-auditoria.md) | Auditabilidade: registros de auditoria isolados e imutáveis | Aceita | 2.3 |
| [002](0002-seguranca.md) | Segurança como propriedade arquitetural | Aceita | 2.1 |
| [003](0003-confiabilidade.md) | Confiabilidade | Aceita | 2.2 |
| [004](0004-recuperabilidade.md) | Recuperabilidade | Aceita | 2.4 |
| [005](0005-arquitetura-baseada-em-servicos.md) | Arquitetura baseada em serviços | Aceita | 3 e 4 |
| [006](0006-aplicacao-web.md) | Aplicação Web | Aceita | 5 |
| [007](0007-verificacao-do-email-do-usuario.md) | Verificação do e-mail do usuário | Aceita | 5 |
| [008](0008-recuperacao-da-conta-por-link-via-email.md) | Recuperação da conta por link via e-mail | Aceita | 5 |
| [009](0009-verificacao-em-multiplas-etapas.md) | Verificação em múltiplas etapas | Aceita | 5 |
| [010](0010-divisao-dos-bancos-de-dados.md) | Divisão dos bancos de dados | Aceita | 5 e 4.1 |
| [011](0011-integridade-das-provas-por-hash.md) | Confirmação da integridade das provas por hash | Aceita | 5 |
| [012](0012-geracao-de-logs-estruturados.md) | Geração de logs estruturados | Aceita | 5 e 4.2.6 |
| [013](0013-pagamento-por-servico-externo.md) | Pagamento por serviço externo | Aceita | 5 e 4.2.2 |

### Desvios e detalhamentos da implementação

| ADR | Título | Status | Afeta | Situação no código | Issue |
|---|---|---|---|---|---|
| [014](0014-mysql-como-banco-de-dados-central.md) | MySQL 8.4 como Banco de Dados Central | Proposta | 010 | Em uso | #2 |
| [015](0015-log-storage-em-database-mysql-separada.md) | Log Storage como database MySQL separada (`veriditi_logs`) | Proposta | 001, 010, 012 | Parcial: database e usuário criados no init | #3, #5 |
| [016](0016-comunicacao-interna-http-fire-and-forget.md) | Comunicação interna por HTTP "fire-and-forget" na Sprint 1 | Proposta | 005, 012 | Planejada | #4 |
| [017](0017-aplicacao-web-nextjs-com-bff.md) | Aplicação Web em Next.js com padrão BFF | Proposta | 006 | Em uso | #12 |
| [018](0018-api-gateway-como-servico-fastapi.md) | API Gateway como serviço FastAPI próprio | Proposta | 005 | Planejada (mock em `apps/web/mock`) | #11 |
| [019](0019-minio-como-object-storage.md) | MinIO como Object Storage | Proposta | 004, 010 | Planejada (Sprint 2) | #26 |
| [020](0020-banco-central-compartilhado-com-posse-por-servico.md) | Banco Central compartilhado com posse por serviço e privilégio mínimo | Proposta | 005, 010, 015 | Em uso | #41 |
| [021](0021-datas-utc-datetime6.md) | Datas em UTC com DATETIME(6) | Proposta | 001 | Em uso | #41 |
| [022](0022-convencoes-do-modelo-fisico.md) | Convenções do modelo físico | Proposta | 014 | Em uso | #41 |
| [023](0023-migrations-por-servico-e-testes-com-mysql.md) | Migrations por serviço e testes com MySQL real | Proposta | 020 | Em uso | #41 |

## Numeração

- **ADRs 002–004:** no documento original, as ADRs de Segurança (2.1), Confiabilidade (2.2) e Recuperabilidade (2.4) aparecem apenas como "ADR", sem número. Como o documento numera a de Auditabilidade como 001 e a de Estilo Arquitetural como 005, elas foram numeradas como 002, 003 e 004 na ordem em que aparecem.
- **Broker de mensagens:** o épico #40 e a issue #37 citam a escolha do Redis Streams como "ADR-020". Esse número foi usado pelo #41 (banco compartilhado). A ADR do broker vai receber o próximo número livre (024 em diante) e substituir a [ADR-016](0016-comunicacao-interna-http-fire-and-forget.md).

## Notas de transcrição

As ADRs 001–013 reproduzem o texto do documento, com ajustes mínimos de ortografia e as consequências separadas em positivas (+) e negativas (−). A seção "Implementação" de cada uma foi acrescentada para ligar a decisão ao código e às issues. Duas inconsistências do original estão sinalizadas no próprio arquivo e precisam de confirmação da equipe arquiteta:

- [ADR-004](0004-recuperabilidade.md): o campo "Decisão" repete o "Contexto".
- [ADR-005](0005-arquitetura-baseada-em-servicos.md): as consequências citam "arquitetura em eventos" em vez de arquitetura baseada em serviços.

## Aceite pendente

As ADRs 014–023 estão como **Proposta**. Para movê-las a **Aceita**:

1. Abrir uma *Discussion* (ou issue) no repositório, ou mandar e-mail para a equipe arquiteta, com o link deste índice.
2. Registrar em cada ADR, na tabela "Aceite da equipe arquiteta", o nome, a data e o link do comentário ou print da aprovação.
3. Só então trocar o Status para **Aceita**.
