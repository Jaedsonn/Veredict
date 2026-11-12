# ADR-022 – Convenções do modelo físico

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-014 (MySQL 8.4 como Banco Central)

## Contexto

Cada issue da Sprint 1 trazia o próprio DDL. Os nomes de índice eram livres (`ix_actor_time`), as PKs variavam (`idempotency_key` como PK no #6) e as representações de hash e UUID não eram uniformes. Sem uma convenção, o `alembic --autogenerate` não compara constraints com nomes gerados pelo MySQL (`users_ibfk_1`), e cada serviço acaba escolhendo tipos diferentes para o mesmo conceito.

## Decisão

- **`naming_convention`** em `veriditi_common.db.make_metadata()`: `pk_<tabela>`, `uq_<tabela>_<cols>`, `ix_<tabela>_<cols>`, `fk_<tabela>_<cols>_<referida>` e `ck_<tabela>_<nome>`. Toda CHECK tem `name=` explícito; sem ele, o SQLAlchemy recusa a constraint.
- **PK substituta** (`id BIGINT AUTO_INCREMENT`) em toda tabela. Chaves naturais, como `idempotency_key` e `event_id`, viram UNIQUE. A deduplicação é a mesma, a PK clusterizada continua curta e sequencial, e os índices secundários não carregam uma chave longa.
- **UUID `CHAR(36)`** para identificadores expostos em URL. **Hashes `CHAR(64)` em hex minúsculo**. Os dois e as chaves de idempotência usam `CHARACTER SET ascii COLLATE ascii_bin`: ocupam 36/64 bytes em vez de até 144/256 em `utf8mb4`, e a comparação é exata. Os tipos `UUIDStr` e `HashHex` aplicam isso. O `sa.Uuid` não serve, porque grava `CHAR(32)` sem hífens no MySQL.
- **`ENUM` nativo** para status (`str_enum`); no SQLite dos testes, `VARCHAR` + CHECK nomeado.
- **FK** obrigatória dentro do serviço, com `RESTRICT`. Entre serviços, nunca (ADR-020).
- **Índices só com uma consulta real** que os justifique, documentada em `docs/banco-de-dados.md`.

## Consequências (positivas / negativas)

- (+) Os nomes são previsíveis: dá para fazer grep, e o autogenerate e o downgrade removem constraints sem surpresa.
- (+) O mesmo model compila para MySQL e SQLite com o comportamento equivalente.
- (−) `ascii_bin` diferencia maiúsculas, então hashes precisam ser normalizados para minúsculas (o `HashHex` faz isso).
- (−) Mudar um `ENUM` (remover ou reordenar valores) exige migration cuidadosa.

## Alternativas consideradas

- **`BINARY(16)` / `BINARY(32)`** para UUID e hash: menor, mas ilegível em consultas e logs, e diverge do contrato do #41, que pede `CHAR`.
- **Chave natural como PK** (`idempotency_key`): PK larga, inserções fora de ordem no índice clusterizado e todos os índices secundários maiores.
- **`VARCHAR` + CHECK também no MySQL**: portável, mas perde a validação compacta e legível do `ENUM`.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| | | |
