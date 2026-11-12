# ADR-017 – Aplicação Web em Next.js com padrão BFF

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-006 (aplicação Web)

## Contexto

A ADR-006 decide por uma aplicação Web "usufruindo das APIs e conexões", e a seção 4.1 coloca a aplicação Web na frente da API Gateway. O documento não define o framework nem onde ficam as credenciais da sessão.

Numa SPA que chama a API direto do navegador, o JWT fica acessível ao JavaScript (`localStorage` ou cookie legível). Um XSS rouba a sessão. Além disso, o refresh token é rotativo e o reuso derruba todas as sessões (#9): várias abas renovando ao mesmo tempo disparariam esse bloqueio.

## Desvio em relação ao documento original

- **Previsto:** aplicação Web que consome as APIs pela API Gateway (ADR-006; seção 4.1).
- **No repositório** (`apps/web`, PRs #42–#47):
  - Next.js 16 (App Router, Server Actions), React 19, TypeScript e Tailwind 4.
  - `src/lib/gateway.ts`: cliente do gateway que só roda no servidor (`server-only`).
  - `src/lib/tokens.ts` e `src/lib/session.ts`: tokens em cookies `httpOnly` (`vrd_access`, `vrd_refresh`).
  - `src/proxy.ts`: renova a sessão antes do render.
  - Deduplicação de refresh por 30 s.
- **Motivação:** segurança (ADR-002) e o comportamento correto com refresh rotativo.

## Decisão

- A aplicação Web é feita em **Next.js** e funciona como **BFF** (*Backend for Frontend*): o navegador só conversa com o servidor Next.js, e só o servidor Next.js conversa com o API Gateway.
- Os tokens ficam em cookies `httpOnly`, `sameSite=lax` e `secure` em produção. **O JavaScript do navegador nunca vê o JWT.**
- A validação dos formulários usa o mesmo schema `zod` no cliente e na Server Action.
- O BFF repassa `X-Forwarded-For` e `User-Agent` para a auditoria (ADR-001).

## Consequências (positivas / negativas)

- (+) Um XSS não consegue ler nem exfiltrar o token.
- (+) Renovação de sessão centralizada, sem disparar a detecção de reuso do refresh.
- (+) A web conhece um único endereço (`GATEWAY_URL`), coerente com a seção 4.1.
- (−) A web precisa de um servidor Node em execução; não pode ser hospedada como site estático.
- (−) Um salto a mais (navegador → Next.js → gateway) em cada requisição.
- (−) Server Actions e `proxy.ts` são específicos do Next.js, o que aumenta o acoplamento ao framework.

## Alternativas consideradas

- **SPA (React/Vite) com o token em memória:** mais simples de hospedar, mas o token fica exposto a XSS e a sessão se perde ao recarregar.
- **SPA com cookie `httpOnly` emitido pelo gateway:** exigiria CORS com credenciais e proteção CSRF no gateway.
- **Páginas renderizadas pelo próprio back-end (Jinja/FastAPI):** abandonaria a experiência interativa e a separação entre web e serviços.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| Beatriz Marques dos Santos | | |
| Danielle Santos de Souza | | |
| Giovanna Ferrúcio Farani | | |
| Luiz Antony Duarte Ribeiro | | |
