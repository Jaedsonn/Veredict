# ADR-004 – Recuperabilidade

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 2.4 (Recuperabilidade). No documento a ADR não tem número; ver o [índice](README.md#numeração).

## Contexto

Um problema crítico que o Veridit poderia apresentar seria as provas em processo de autenticação ou já autenticadas serem perdidas ou comprometidas, tendo em vista que o usuário já pagou por elas.

## Decisão

> **Nota de transcrição:** no documento original, o campo "Decisão" repete o texto do "Contexto". A decisão abaixo é a que o próprio documento descreve nas consequências desta ADR e formaliza na [ADR-010](0010-divisao-dos-bancos-de-dados.md). A redação precisa ser confirmada pela equipe arquiteta.

Separar o armazenamento em dois bancos: um com as provas, gravações e imagens, e outro, relacional, com as informações do cliente, pagamento e relatório, de forma que um problema no banco estruturado não afete a existência e a veracidade das provas.

## Consequências (positivas / negativas)

- (+) Esse recurso é importante para garantir que qualquer problema que exista no banco estruturado não impacte a existência e a veracidade das provas.
- (−) Essa decisão vai implicar em mais operações para ligar as informações de cada banco de dados, um com as provas, gravações e imagens e o outro relacional com as informações do cliente, pagamento e relatório. Ou seja, exigirá uma complexidade a mais na hora da implementação.

## Implementação

- Object Storage com Object Lock: [ADR-019](0019-minio-como-object-storage.md) (Sprint 2, #26).
- Backups diários para fora da máquina: Sprint 2 (#37).
