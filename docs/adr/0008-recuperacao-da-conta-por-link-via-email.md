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

- Sprint 2: #19 (back-end) e a parte de recuperação do #20 (telas).
- Back-end (`services/auth`, `use_cases/password_reset.py`):
  - `POST /auth/password/forgot {email}` responde sempre `202 {"status":"accepted"}`. Só conta `active` recebe link; conta inexistente, `pending_verification` ou `blocked` não grava nada e gera só a auditoria `auth.password.reset_requested` com `outcome=failure` e o motivo, sem o e-mail.
  - O token é `secrets.token_urlsafe(32)` (256 bits). O banco guarda só o SHA-256 (`password_reset_tokens`, `docs/banco-de-dados.md` §5.6); com essa entropia o pepper é dispensável. Vale 30 min (`PASSWORD_RESET_TTL_MINUTES`), é de uso único, e um pedido novo consome os anteriores.
  - `POST /auth/password/reset {token, new_password}`: a `PasswordPolicy` roda antes de consumir o link, então senha fraca dá `422` e o link continua valendo. Depois, numa transação só: consumo condicional do token, troca do hash e revogação de todos os refresh tokens com `revoke_reason = 'password_reset'`. Sucesso → `204` e e-mail `password_changed`.
  - Token malformado, inexistente, expirado, usado ou substituído dá sempre `400 invalid_reset_token`; o motivo real vai só para `auth.password.reset_failed`. O sucesso é `auth.password.reset_completed`, com o número de sessões revogadas. Token e senha nunca vão para resposta, log ou auditoria (as chaves `token` e `new_password` caem no `redact_sensitive` da lib comum).
  - Os e-mails saem depois da resposta (`BackgroundNotifier`), para o tempo do `202` não denunciar se a conta existe. Resta a diferença das escritas no banco, só para conta ativa.
- Gateway: o forgot tem 10 pedidos por hora por IP e 3 por hora por e-mail (de qualquer IP), nessa ordem; o reset tem 10 por hora por IP. O `Retry-After` vem do token bucket (1200 s no limite por e-mail).
- Notification: templates `password_reset` (link `{WEB_URL}/redefinir-senha?token=…`) e `password_changed` ("se não foi você").
- Web: `/esqueci-senha` (mensagem neutra) e `/redefinir-senha` (nova senha, confirmação e indicador de força; link inválido mostra o atalho para pedir outro). A rota de reset sai com `Referrer-Policy: no-referrer` e `Cache-Control: no-store` (`next.config.ts`), mais meta `referrer` e `noindex`. `/entrar` tem o link "Esqueci minha senha".
- Limites conhecidos:
  - O access token JWT já emitido continua válido até expirar (no máximo 15 min), porque o gateway o valida sem consultar o auth; só os refresh tokens caem na hora.
  - O token fica na URL: pode ir para o histórico do navegador. Mitigam a `Referrer-Policy`, os 30 min e o uso único.
  - O rate limit é por processo do gateway (memória): réplicas multiplicam o limite e um restart o zera.
  - Tempo residual no forgot: o e-mail já sai em background, mas a conta ativa ainda paga o lock do usuário, o UPDATE dos tokens antigos, o INSERT e o commit, enquanto a inexistente responde depois de um SELECT. A diferença é de milissegundos, fica no ruído da rede, e os 3 pedidos por hora por e-mail tornam impraticável medi-la repetidas vezes.
  - Custo do reset: a senha nova passa pela política e pelo Argon2 antes de o banco ser consultado (senha fraca não pode queimar o link), então um token bem-formado e inexistente custa um hash inteiro. Os 10 pedidos por hora por IP limitam esse uso como amplificador de CPU.
  - MFA (#18) ainda não existe. Quando entrar, o reset não pode desligá-lo: o próximo login continua exigindo o 2º fator.
