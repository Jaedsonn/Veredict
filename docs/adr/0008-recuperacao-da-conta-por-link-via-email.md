# ADR-008 – Recuperação da conta por link via e-mail

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões)

## Contexto

No contexto de contas de usuário, é necessário permitir a recuperação da conta caso o usuário não lembre da senha, ou exista a necessidade.

## Decisão

Utilizar o e-mail verificado do usuário para a recuperação da conta, baseado na geração de um token de recuperação incorporado em um link e enviado por e-mail.

## Consequências (positivas / negativas)

- (+) Permite que o usuário tenha maior facilidade com a recuperação de senha, sendo mais conveniente.
- (−) Abre um vetor de ataque maior, considerando que, caso haja uma falha de segurança relacionada ao e-mail do usuário, isso pode comprometer a conta desse usuário no sistema.

## Implementação

- Sprint 2: #19 (back-end) e #20 (telas).
