# ADR-020 – Banco Central compartilhado com posse por serviço e privilégio mínimo

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-005 (arquitetura baseada em serviços), ADR-010 (camada de dados), ADR-015 (Log Storage)

## Contexto

O documento de arquitetura define um **Banco de Dados Central** acessado por autenticação, pagamento, captura e armazenamento (ADR-010). A arquitetura baseada em serviços (ADR-005) admite banco compartilhado, mas o banco vira o ponto de acoplamento entre serviços: qualquer um pode ler e alterar tabelas de outro, e uma mudança de schema afeta todos.

Até o #41, o repositório tinha um único usuário MySQL (`MYSQL_USER`) com `ALL` em `veriditi`, usado inclusive pela aplicação em execução, que portanto tinha DDL.

A mitigação recomendada para banco compartilhado é particioná-lo logicamente por domínio e restringir quem muda cada parte (Richards & Ford, *Fundamentals of Software Architecture*, cap. 13). Há um detalhe do MySQL que pesa na decisão: `GRANT SELECT ON db.tabela` falha se a tabela não existe (só passa quando inclui `CREATE`), e no initdb as tabelas ainda não existem.

## Decisão

1. **Banco compartilhado, posse por tabela.** A matriz de posse de `docs/banco-de-dados.md` é a fonte da verdade. Entre serviços, só há referência lógica por ID, API ou evento, **sem FOREIGN KEY**.
2. **Um usuário MySQL por serviço**, criado por `docker/mysql/init/02-service-users.sh`: `auth_svc`, `notification_svc` e `veriditi_logs_writer` na Sprint 1; `payment_svc`, `capture_svc` e `storage_svc` na Sprint 2. Nenhum recebe privilégio no init.
3. **Um `migrator`** com DDL + DML `WITH GRANT OPTION` em `veriditi.*` e `veriditi_logs.*`. É o único usuário que o Alembic usa.
4. **O GRANT nasce na migration que cria a tabela**, com o helper `veriditi_common.migrations`. O `downgrade` revoga antes do `DROP`, porque o MySQL não revoga GRANT de tabela apagada.
5. **Privilégios mínimos por tabela**: só o DML que o caso de uso precisa. Auditoria, ledger e provas são append-only (`SELECT, INSERT`).

## Consequências (positivas / negativas)

- (+) O isolamento é verificável: `make db-test-contract` prova que um serviço não lê tabela de outro (erro 1142) e que o `auth_svc` não abre o `veriditi_logs` (erro 1044).
- (+) Tabela e permissão evoluem juntas, no mesmo PR do serviço dono.
- (+) Separar fisicamente um serviço no futuro fica barato: as tabelas dele já não têm FK nem leitores externos.
- (−) O `migrator` com `GRANT OPTION` é a credencial mais sensível depois do root.
- (−) Um usuário sem nenhum GRANT não conecta ao banco. O container de migração de cada serviço precisa terminar antes de o serviço subir.
- (−) O acoplamento de servidor continua: disponibilidade e recursos são compartilhados.

## Alternativas consideradas

- **Um schema por serviço** (`veriditi_auth`, …): o GRANT por schema funcionaria no init, mas contraria os dois bancos lógicos da ADR-010 e do #41.
- **Script central de GRANTs com root depois das migrations**: exige credencial root num container extra e alguém precisa lembrar de atualizá-lo a cada tabela nova.
- **GRANT com `CREATE` no init**: daria DDL ao runtime, o oposto do objetivo.
- **Manter o usuário único**: nenhum isolamento; um bug no pagamento poderia ler `refresh_tokens`.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| | | |
