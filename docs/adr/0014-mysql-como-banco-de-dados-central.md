# ADR-014 – MySQL 8.4 como Banco de Dados Central

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-010 (divisão dos bancos de dados)

## Contexto

A ADR-010 pede para os dados estruturados "uma solução madura, com boa performance e suporte nativo a dados estruturados e semiestruturados", com consultas complexas e relacionamentos bem definidos entre usuários, pedidos e pagamentos. O documento não nomeia o SGBD. O repositório foi criado já com MySQL, e essa escolha nunca foi registrada.

## Desvio em relação ao documento original

- **Previsto:** um "Banco de dados central" relacional (seção 4.1 e ADR-010), sem tecnologia definida.
- **No repositório:** MySQL 8.4 com InnoDB e `utf8mb4`. O serviço `mysql` usa a imagem `mysql:8.4` no `docker-compose.yml`. Os serviços conectam com `mysql+aiomysql` (`libs/python/common/src/veriditi_common/settings.py`) e versionam o schema com Alembic.
- **Motivação:** formalizar uma escolha que o documento deixou em aberto. Não contraria a ADR-010; é um detalhamento.

## Decisão

Usar **MySQL 8.4** (versão LTS) como SGBD do Banco Central e, pela [ADR-015](0015-log-storage-em-database-mysql-separada.md), também do Log Storage:

- engine InnoDB (transações ACID e chaves estrangeiras dentro de cada serviço);
- charset `utf8mb4` / `utf8mb4_0900_ai_ci`;
- tipo `JSON` nativo para os dados semiestruturados citados na ADR-010 (por exemplo, o `metadata` dos eventos de auditoria);
- driver assíncrono `aiomysql` com SQLAlchemy 2, compatível com o FastAPI.

As convenções físicas (tipos, nomes, datas) estão nas ADRs [021](0021-datas-utc-datetime6.md) e [022](0022-convencoes-do-modelo-fisico.md).

## Consequências (positivas / negativas)

- (+) Atende aos requisitos da ADR-010: banco maduro, relacional, com `JSON` nativo.
- (+) Imagem oficial no Docker; o ambiente sobe com `make db` / `make up`.
- (+) Uma tecnologia só para os dois bancos lógicos (central e logs) reduz a operação.
- (−) Recursos que o PostgreSQL teria prontos não existem no MySQL (`TIMESTAMPTZ`, CHECK com subconsulta, `RETURNING`). O fuso foi resolvido na aplicação (ADR-021).
- (−) `GRANT` de tabela só funciona com a tabela já criada, o que moldou a estratégia de privilégios da ADR-020.
- (−) Os testes unitários rodam em SQLite. A diferença é coberta pelos testes de contrato com MySQL real (ADR-023).

## Alternativas consideradas

- **PostgreSQL:** tipos mais ricos e `TIMESTAMPTZ`; seria igualmente adequado. Ficou o MySQL porque o template do repositório e a modelagem do #41 já foram feitos sobre ele.
- **MariaDB:** compatível, mas diverge do MySQL 8 em `JSON` e collations `0900`.
- **SQLite em produção:** não suporta vários serviços escrevendo em paralelo nem usuários e privilégios.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| Beatriz Marques dos Santos | | |
| Danielle Santos de Souza | | |
| Giovanna Ferrúcio Farani | | |
| Luiz Antony Duarte Ribeiro | | |
