# ADR-021 – Datas em UTC com DATETIME(6), garantidas na aplicação, na sessão e no servidor

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-001 (data e hora precisas da captura)

## Contexto

A ADR-001 exige data e hora precisas para o valor probatório das capturas. O model inicial usava `DateTime(timezone=True)` + `func.now()`. No MySQL, `timezone=True` é ignorado: a coluna vira `DATETIME` sem fuso e sem fração, e `NOW()` depende do `time_zone` da sessão. As issues #7, #8 e #9 usavam `DATETIME` sem fração. Os testes rodam em SQLite, que não tem tipo de data nativo.

Timestamps só são comparáveis entre máquinas quando expressos numa referência comum, como UTC (Kleppmann, *Designing Data-Intensive Applications*, cap. 8).

## Decisão

Toda coluna temporal é `DATETIME(6)` em UTC, e o default de servidor é `CURRENT_TIMESTAMP(6)` (o MySQL exige o mesmo fsp no tipo e no default). A garantia de UTC é feita em três camadas:

1. **Aplicação** (principal): o tipo `veriditi_common.db_types.UTCDateTime` recusa datetime *naive*, converte qualquer fuso para UTC antes de gravar e devolve datetime *aware* em UTC na leitura. O default do lado Python é `utcnow()`.
2. **Sessão**: `create_service_engine` executa `SET time_zone = '+00:00'` em toda conexão MySQL. Defaults de servidor e SQL manual também saem em UTC.
3. **Servidor** (defesa extra): o MySQL sobe com `--default-time-zone=+00:00` (compose do #3).

O `server_default` dos models usa `UtcNow()`, que vira `CURRENT_TIMESTAMP(6)` no MySQL e `STRFTIME(... 'now')` no SQLite. As migrations escrevem `sa.text("CURRENT_TIMESTAMP(6)")`.

## Consequências (positivas / negativas)

- (+) O instante gravado não depende de onde o código roda, e os microssegundos ordenam eventos do mesmo segundo (`audit_events.occurred_at`).
- (+) O mesmo model funciona em MySQL e em SQLite.
- (−) Passar um datetime naive falha na hora do flush. É intencional, mas exige atenção em testes e scripts.
- (−) Conversão de fuso para exibição fica sempre a cargo da web.

## Alternativas consideradas

- **`TIMESTAMP(6)`**: converte pelo fuso da sessão (o mesmo problema, escondido) e estoura em 2038.
- **`BIGINT` com epoch em µs**: portável, mas ilegível em consultas manuais e sem as funções de data do MySQL.
- **Confiar só no fuso do servidor**: um ambiente gerenciado com outro `time_zone` quebraria silenciosamente.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| | | |
