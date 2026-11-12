# ADR-023 – Migrations por serviço e testes com MySQL real

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-020 (posse por serviço)

## Contexto

Vários serviços criam tabelas no mesmo servidor MySQL. Com a tabela de versão padrão do Alembic (`alembic_version`), um serviço sobrescreveria a revisão do outro. Os testes unitários rodam em SQLite, que não tem usuários, GRANTs nem `DATETIME(6)`, então os critérios de privilégio mínimo e de UTC não podem ser provados ali.

## Decisão

- **Uma pasta `migrations/` e uma `version_table` por serviço** (`alembic_version_<serviço>`), com histórico linear (1 head).
- **Migrations não importam models**: usam tipos físicos explícitos. **A tabela e o GRANT nascem na mesma revisão**, e o `downgrade` revoga antes do `DROP`.
- **Revisão mergeada é imutável.** A única exceção é o rebaseline do #3 (`users` → `auth`), feito antes de existir qualquer ambiente implantado.
- **Duas camadas de teste**:
  - SQLite (`uv run pytest`): comportamento dos tipos, convenção de nomes e helpers. É rápido e roda em todo PR.
  - MySQL real (marcador `mysql`, `make db-test-contract`): privilégios (erros 1142 e 1044), sessão em UTC, collation e DDL físico. Sobe um `mysql:8.4` descartável com `docker/mysql/init`.
- **CI** (job `database`, a criar no #3): para cada serviço, `alembic heads` → `upgrade head` → `alembic check` → `downgrade base` → `upgrade head`, e depois os testes `mysql`.

## Consequências (positivas / negativas)

- (+) Os critérios de segurança do #41 são testes automatizados, não só documentação.
- (+) Um `downgrade` quebrado ou um segundo head são detectados antes do merge.
- (−) Os testes `mysql` precisam de Docker e ficam fora do `pytest` padrão; é preciso lembrar de rodá-los localmente até o CI do #3 existir.
- (−) Dois PRs que criam revisões em paralelo no mesmo serviço exigem rebase e renumeração.

## Alternativas consideradas

- **Testcontainers no pytest**: subiria o MySQL a partir do próprio teste, mas traz mais uma dependência e fica mais lento por sessão. O `docker run` do Makefile basta e é o mesmo comando que o CI vai usar.
- **Só SQLite**: não prova nenhum critério de privilégio nem o DDL físico.
- **Uma única pasta de migrations para todos os serviços**: acopla o deploy dos serviços e contraria a posse por serviço.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| | | |
