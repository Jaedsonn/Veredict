# ADR-011 – Confirmação da integridade das provas por hash

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões)

## Contexto

Considerando a sensibilidade dos dados armazenados, é importante que o usuário tenha certeza de que os registros feitos não foram alterados pelo sistema ou por agentes externos.

## Decisão

Para todo dado capturado (vídeo ou foto), ao final da captura será calculado um hash, com base em um algoritmo moderno, e esse valor será armazenado pelo sistema e disponibilizado para o usuário.

## Consequências (positivas / negativas)

- (−) Fazer o cálculo do hash pode ser custoso dependendo do dado capturado, o que pode influenciar negativamente a experiência do usuário considerando o tempo computacional.
- (−) É mais um dado a ser armazenado, o que deve ser considerado.
- (+) A existência do hash permite uma maior confiabilidade do usuário na plataforma, considerando que ele pode verificar por conta própria a imutabilidade da captura.

## Implementação

- Sprint 2: SHA-256 calculado pelo serviço de armazenamento durante o upload (#27) e verificação pública (#28). Hashes gravados como `CHAR(64)` hex ([ADR-022](0022-convencoes-do-modelo-fisico.md)).
