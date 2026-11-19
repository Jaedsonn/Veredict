# ADR-025 – Provedor PIX sandbox e dados de faturamento sem CPF em claro

- Status: Proposta
- Data: 2026-11-19
- Afeta: ADR-013 (pagamento por serviço externo), ADR-024 (cifragem do CPF)

## Contexto

O REQ05 do Documento de Requisitos (comprar créditos) foi antecipado para a Sprint 1. A compra tem três passos: escolher o pacote, informar os dados de faturamento e pagar. A ADR-013 decide por um checkout transparente com PIX por um serviço externo, que guarda os dados de pagamento. O ambiente da Sprint 1 não tem credenciais de nenhum provedor (Mercado Pago, Asaas ou Efí), e a demonstração precisa do fluxo completo. O Apêndice A pede o CPF entre os dados da compra, e a ADR-024 já trata o CPF como dado que não fica em claro no banco.

## Desvio em relação ao documento original

- **Previsto:** pagamento por API externa com QR Code ou PIX copia-e-cola ("Estruturação do Veridit", seção 5 e 4.2.2).
- **No repositório:** a cobrança passa pela porta `PaymentProvider` (`services/payment/src/payment_service/ports.py`). Na Sprint 1 o único adapter é o `SandboxPixProvider` (`adapters/sandbox_provider.py`). Ele gera um copia-e-cola no formato BR Code, com CRC16, e o QR Code em SVG, sem cobrar nada. A confirmação vem do botão "Simular pagamento" (`POST /api/orders/{id}/simulate-payment`), que só existe com `PAYMENT_PROVIDER=sandbox`.
- **Motivação:** entregar o REQ05 de ponta a ponta sem credenciais de produção, mantendo o ponto de troca para o provedor real (#23).

## Decisão

1. O pagamento fica atrás de `PaymentProvider`. Trocar o sandbox pelo provedor real é escolher outro adapter em `main.py` pela variável `PAYMENT_PROVIDER`, sem mudar casos de uso (DIP).
2. A confirmação (`ConfirmPayment`) é a mesma para o sandbox e para o webhook do provedor real (#23): pedido `pending → paid` e crédito no ledger na mesma transação, idempotente.
3. Os dados de faturamento do Apêndice A ficam no pedido (`orders.billing_*`), **com o CPF só mascarado** (`***.982.247-**`). O CPF completo existe apenas em memória e vai ao provedor, que é quem guarda os dados de pagamento (ADR-013).

## Consequências (positivas / negativas)

- (+) O REQ05 é demonstrável inteiro, com o mesmo contrato de API que o provedor real vai usar.
- (+) O banco do Veriditi não guarda CPF de faturamento em claro nem precisa de uma segunda chave de cifra.
- (−) Nenhum dinheiro real circula até a #23. A tela avisa "Ambiente de demonstração" quando o provedor é o sandbox.
- (−) Uma nota fiscal futura que precise do CPF completo terá de buscá-lo no provedor ou no perfil (auth), e não no pedido.

## Alternativas consideradas

- **Sandbox do Mercado Pago:** exige conta e credenciais de teste no ambiente de cada desenvolvedor e no CI. Entra com a #23.
- **Guardar o CPF cifrado no pedido (como a ADR-024):** duplicaria a gestão de chaves em outro serviço sem uso real na Sprint 1.

## Aceite da equipe arquiteta

| Integrante | Evidência |
|---|---|
| | |
