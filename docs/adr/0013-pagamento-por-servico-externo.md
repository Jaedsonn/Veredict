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

- Sprint 1 (REQ05): serviço `services/payment` com catálogo (#21), pedido PIX (#22), carteira (#73) e telas (#25). O provedor PIX fica atrás da porta `PaymentProvider`; na Sprint 1 o adapter é o sandbox ([ADR-025](0025-provedor-pix-sandbox-e-faturamento.md)).
- Sprint 2: provedor real e webhook assinado (#23); débito e estorno da captura (#24).
