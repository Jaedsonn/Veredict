# ADR-007 – Verificação do e-mail do usuário

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões)

## Contexto

É necessário garantir que o usuário exista, que foi ele mesmo quem realizou o cadastro e que o e-mail será válido para funções como recuperar a conta e receber confirmação de gravação do conteúdo, garantindo as características de segurança.

## Decisão

Para que esse contexto seja atingido, será realizada uma verificação do e-mail do usuário no momento em que ele está fazendo o cadastro. Essa verificação consistirá no envio de um código por e-mail, que será digitado no site. Dentre as possibilidades, o e-mail foi escolhido como o meio por ser considerado mais seguro do que SMS ou WhatsApp, já que é necessário um login.

## Consequências (positivas / negativas)

- (−) Adiciona mais uma etapa ao usuário e torna o processo de cadastro um pouco mais demorado.
- (+) É essencial para garantir a segurança do dono do e-mail e impede que outras pessoas usem endereços de e-mail indevidamente.

## Implementação

- Web: tela `/verificar-email` com código de 6 dígitos (`apps/web/src/app/(public)/verificar-email/`, #13).
- Back-end: #8 (código) e #6 (envio do e-mail).
- Tabela `email_verification_codes`: `docs/banco-de-dados.md`, seção 5.2.
