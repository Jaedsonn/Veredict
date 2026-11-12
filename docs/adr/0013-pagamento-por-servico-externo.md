# ADR-013 – Pagamento por serviço externo

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões); serviço de pagamento na seção 4.2.2

## Contexto

Como o Veridit apresenta a possibilidade de compra de créditos para as gravações e capturas e determina que o pagamento é efetuado via QR Code ou código PIX copia e cola diretamente na aplicação web, é interessante a integração com outras APIs para pagamento.

## Decisão

Utilizaremos um checkout transparente, com as informações aparecendo diretamente na interface do Veridit.

## Consequências (positivas / negativas)

- (+) Garante mais segurança, tendo em vista que as informações de pagamento serão guardadas por APIs externas.

## Implementação

- Sprint 2: #21–#24 (serviço de pagamento) e #25 (telas). O provedor PIX fica atrás de uma interface `PaymentProvider`, e a escolha do provedor será registrada numa nova ADR (#22).
