# ADR-002 – Segurança como propriedade arquitetural

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 2.1 (Segurança). No documento a ADR não tem número; ver o [índice](README.md#numeração).

## Contexto

Como o Veridit é um sistema de ações burocráticas, é necessário que os dados e a identidade do usuário sejam preservados, assim como a garantia de que é o próprio cliente que está usando a aplicação e não uma invasão.

## Decisão

Para garantir que problemas relacionados a isso não ocorram, é necessário garantir que a segurança esteja como uma das propriedades arquiteturais no desenvolvimento do sistema.

## Consequências (positivas / negativas)

- (+) A segurança passa a orientar as demais decisões. Algumas consequências e ações a serem tomadas tendo em vista essa característica:
  - autenticação em duas etapas pelo e-mail no momento do cadastro ([ADR-007](0007-verificacao-do-email-do-usuario.md));
  - recuperação de conta via e-mail, caso o usuário esqueça a senha ([ADR-008](0008-recuperacao-da-conta-por-link-via-email.md)).

## Implementação

- Sessão no servidor da web, com o JWT só em cookie `httpOnly`: [ADR-017](0017-aplicacao-web-nextjs-com-bff.md).
- Validação do JWT e rate limit centralizados: [ADR-018](0018-api-gateway-como-servico-fastapi.md).
- Privilégio mínimo no banco: [ADR-020](0020-banco-central-compartilhado-com-posse-por-servico.md).
