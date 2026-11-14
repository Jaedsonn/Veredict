# ADR-023 – Migrations por serviço e testes com MySQL real

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-020 (posse por serviço)

## Contexto

Vários serviços criam tabelas no mesmo servidor MySQL. Com a tabela de versão padrão do Alembic (`alembic_version`), um serviço sobrescreveria a revisão do outro. Os testes unitários rodam em SQLite, que não tem usuários, GRANTs nem `DATETIME(6)`, então os critérios de privilégio mínimo e de UTC não podem ser provados ali.

## Decisão

- **Uma pasta `migrations/` e uma `version_table` por serviço** (`alembic_version_<serviço>`), com histórico linear: no máximo 1 head (0 enquanto o serviço ainda não tem revisão).
- **Migrations não importam models**: usam tipos físicos explícitos. **A tabela e o GRANT nascem na mesma revisão**, e o `downgrade` revoga antes do `DROP`.
- **Revisão mergeada é imutável.** A única exceção é o rebaseline do #3 (`users` → `auth`), feito antes de existir qualquer ambiente implantado.
- **Duas camadas de teste**:
  - SQLite (`uv run pytest`): comportamento dos tipos, convenção de nomes e helpers. É rápido e roda em todo PR.
  - MySQL real (`make db-test`), num `mysql:8.4` descartável com `docker/mysql/init`, em duas etapas:
    1. `make db-test-contract`: testes com o marcador `mysql` (privilégios com os erros 1142 e 1044, sessão em UTC, collation, DDL físico e as migrations com GRANT/REVOKE);
    2. `make db-test-migrations`: para cada serviço com `alembic.ini`, `alembic heads` (no máximo 1 linha) → `upgrade head` → `alembic check` → `downgrade base` → `upgrade head`, e confere que a `alembic_version_<serviço>` existe no banco do serviço.
- **CI**: o job `database` (criado no #3) roda o mesmo `make db-test`.
- **Cobertura** (#15): o job `tests` roda `make cov s=<alvo>` em matriz, com mínimo de 70% por serviço e na lib comum, só sobre a camada SQLite. Os testes `mysql` não entram na medição.

## Consequências (positivas / negativas)

- (+) Os critérios de segurança do #41 são testes automatizados, não só documentação.
- (+) Um `downgrade` quebrado ou um segundo head são detectados antes do merge.
- (−) Os testes `mysql` precisam de Docker e ficam fora do `pytest` padrão; localmente é preciso lembrar do `make db-test`, e o job `database` cobre o PR.
- (−) Dois PRs que criam revisões em paralelo no mesmo serviço exigem rebase e renumeração.

## Alternativas consideradas

- **Testcontainers no pytest**: subiria o MySQL a partir do próprio teste, mas traz mais uma dependência e fica mais lento por sessão. O `docker run` do Makefile basta e é o mesmo comando que o CI usa.
- **Só SQLite**: não prova nenhum critério de privilégio nem o DDL físico.
- **Uma única pasta de migrations para todos os serviços**: acopla o deploy dos serviços e contraria a posse por serviço.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| | | |
