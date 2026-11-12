# ADR-005 – Arquitetura baseada em serviços

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 3 (Estilo arquitetural) e seção 4 (Componentes candidatos)

## Contexto

O Veridit atualmente é um sistema pequeno e desenvolvido por alunos, então algumas coisas precisam ser levadas em consideração, como por exemplo não ser uma implementação extremamente complexa e uma aplicação muito grande sem essa necessidade atualmente. Outra motivação essencial do sistema é que realize gravações de tela e que essa ação mais pesada não comprometa o sistema como um todo.

## Decisão

Pensando nas arquiteturas estudadas, foi escolhida a Arquitetura Baseada em Serviços (Service-Based). Tendo em vista que será possível separar cada necessidade como bloco de serviços maiores, dividindo as funções, mas também não será extremamente dividido como em microsserviços, pois, como é um sistema inicial, não há necessidade de uma aplicação tão robusta. A divisão dos serviços também garante que, se um falhar, os outros seguem funcionando sem interrupções, ou seja, confiabilidade. Além disso, a possibilidade de divisão do banco de dados garante a recuperabilidade. A segurança pode ser garantida dedicando um serviço para a identificação do usuário.

Componentes definidos (seção 4):

1. Serviço de autenticação
2. Serviço de pagamento
3. Serviço de notificações
4. Serviço de captura
5. Serviço de armazenamento
6. Serviço de monitoramento
7. API Gateway

A API Gateway só tem acesso a autenticação, pagamento, captura e armazenamento. Notificação e monitoramento têm acionamento interno e não são expostos ao usuário (seção 4.1).

## Consequências (positivas / negativas)

- (−) Em relação a um sistema monolítico, a arquitetura terá uma implementação mais complexa e as transmissões não serão automáticas.
- (+) A divisão em serviços será essencial para o funcionamento adequado da aplicação.

> **Nota de transcrição:** o documento original diz "a arquitetura em eventos" nas consequências. Pelo contexto, a frase se refere à arquitetura baseada em serviços escolhida nesta ADR.

## Implementação

- Monorepo com um diretório por serviço em `services/` e infraestrutura comum em `libs/python/common` (só infraestrutura, nunca regra de negócio).
- Hoje existe apenas o template `services/users`; os serviços da Sprint 1 nascem no #3.
- Desvios e detalhamentos: [ADR-016](0016-comunicacao-interna-http-fire-and-forget.md), [ADR-018](0018-api-gateway-como-servico-fastapi.md) e [ADR-020](0020-banco-central-compartilhado-com-posse-por-servico.md).
