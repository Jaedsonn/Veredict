# ADR-015 – Log Storage como database MySQL separada (`veriditi_logs`)

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-001 (auditabilidade), ADR-010 (divisão dos bancos), ADR-012 (logs estruturados)

## Contexto

A ADR-001 exige que os registros de auditoria fiquem isolados dos logs comuns e que ninguém possa editá-los ou apagá-los. A seção 4.1 do documento define um "Armazenamento de logs" separado do Banco Central, imutável e acessado só pelo serviço de monitoramento. O documento não diz que tecnologia garante essa imutabilidade.

## Desvio em relação ao documento original

- **Previsto:** um armazenamento de logs próprio, imutável, acessado só pelo monitoramento (seção 4.1; ADR-001).
- **No repositório:**
  - `docker/mysql/init/01-logs-db.sql` cria a database `veriditi_logs` no mesmo servidor MySQL do Banco Central.
  - `docker/mysql/init/02-service-users.sh` cria o usuário `veriditi_logs_writer`, sem privilégio nenhum. O `GRANT SELECT, INSERT` nasce na migration do monitoring que cria `audit_events` (#5), pela regra da [ADR-020](0020-banco-central-compartilhado-com-posse-por-servico.md).
  - `make db-test-contract` prova que o `auth_svc` não abre `veriditi_logs` (erro 1044).
  - O serviço de monitoramento existe desde o #5. A migration `0001` cria `audit_events` e roda no `monitoring-migrate` como **`migrator`**, o único usuário com DDL. O `LOGS_DB_MIGRATOR_*` da issue não existe: um único `migrator` serve aos dois bancos (`docs/banco-de-dados.md` §14).
  - O app roda como **`veriditi_logs_writer`**, com só `SELECT, INSERT` em `audit_events`, concedidos na mesma revisão.
  - `services/monitoring/tests/mysql/test_audit_events_mysql.py` prova o erro 1142 em `UPDATE`, `DELETE`, `TRUNCATE` e `ALTER`, e o REVOKE no downgrade.
- **Motivação:** obter o isolamento e a imutabilidade pedidos sem acrescentar uma nova tecnologia de armazenamento na Sprint 1.

## Decisão

- O Log Storage é a **database `veriditi_logs`**, no mesmo servidor MySQL 8.4 do Banco Central ([ADR-014](0014-mysql-como-banco-de-dados-central.md)).
- A **imutabilidade é garantida pelo banco**: o runtime do monitoring usa `veriditi_logs_writer`, com só `SELECT` e `INSERT` na trilha de auditoria. Não há `UPDATE` nem `DELETE`, nem para o próprio serviço.
- Nenhum outro serviço tem usuário com acesso a `veriditi_logs`.
- Logs operacionais (`operational_logs`, Sprint 2) ficam na mesma database. Só a rotina de limpeza (#35) recebe `DELETE`, e apenas nessa tabela.

## Consequências (positivas / negativas)

- (+) Um bug ou invasão no serviço não consegue alterar nem apagar a auditoria: o MySQL recusa o comando.
- (+) A separação é verificável por teste automatizado (ADR-023).
- (+) Sem novo componente para operar, monitorar e fazer backup.
- (−) O servidor é compartilhado: se o MySQL cair, caem juntos o Banco Central e o Log Storage. Isso contraria parcialmente a ideia de isolamento físico da ADR-010.
- (−) Quem tem o `root` ou o `migrator` ainda consegue alterar registros. A mitigação é o encadeamento de hash dos eventos (#34), que torna qualquer adulteração detectável, e o arquivamento em Object Storage (`log-archive`, Sprint 2).
- (−) O crescimento contínuo da tabela (já previsto na ADR-001) exige política de retenção (#35).

## Alternativas consideradas

- **Instância MySQL separada:** isolamento físico total, mas dobra a operação na Sprint 1.
- **Armazenamento WORM em object storage** (arquivo append-only com Object Lock): imutável de verdade, mas sem consultas para a trilha de auditoria (RF20).
- **Stack de logs** (Elasticsearch, Loki): boa para logs operacionais, mas não dá a garantia de não edição que a ADR-001 exige.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| Beatriz Marques dos Santos | | |
| Danielle Santos de Souza | | |
| Giovanna Ferrúcio Farani | | |
| Luiz Antony Duarte Ribeiro | | |
