# ADR-009 – Verificação em múltiplas etapas

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões)

## Contexto

O sistema precisa garantir a autenticidade do usuário que acessa, mantendo a segurança das informações e permitindo que os registros feitos não tenham sido manipulados.

## Decisão

Implementar e tornar obrigatória a verificação de múltiplos fatores, de forma mista (e-mail, autenticador, etc.).

## Consequências (positivas / negativas)

- (+) Permite uma maior confiabilidade no usuário, garantindo a autenticidade das interações e aumentando a segurança geral do sistema.
- (−) Afeta a experiência do usuário no sentido de "dificultar" o acesso ao sistema, levando mais tempo e necessitando mais atenção e passos extras para o login e o cadastro.

## Implementação

- Sprint 2: #18 (TOTP com fallback por e-mail) e #20 (telas). O componente `OtpInput` da web já foi feito para ser reutilizado no MFA.
