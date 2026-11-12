# ADR-018 – API Gateway como serviço FastAPI próprio

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-005 (arquitetura baseada em serviços)

## Contexto

O documento define a API Gateway como "responsável pela comunicação entre a aplicação WEB (o usuário) e os demais serviços, distribuindo as requisições" (seção 4, item 7). Ela só enxerga autenticação, pagamento, captura e armazenamento (seção 4.1). O documento não define a tecnologia.

Além de rotear, o gateway precisa validar o JWT de toda chamada, aplicar rate limit no login (RNF01) e propagar a identidade do usuário e o `X-Request-ID` aos serviços.

## Desvio em relação ao documento original

- **Previsto:** um componente API Gateway, sem tecnologia definida (seções 4 e 4.1).
- **No repositório:**
  - O gateway é o serviço `services/gateway` (esqueleto no #3, roteamento no #11).
  - A web só conhece `GATEWAY_URL` (`apps/web/src/lib/config.ts`), que no compose é `http://gateway:8000`.
  - A tabela de rotas, a validação do JWT RS256, o rate limit e a propagação de contexto estão descritos no README ("API Gateway").
  - O mock `apps/web/mock/gateway.mjs` (PR #44) continua para desenvolver a web sem o auth.
- **Motivação:** usar a mesma stack dos serviços (Python/FastAPI e `veriditi_common`) para validação de JWT, regras de autorização e logging estruturado.

## Decisão

Implementar a API Gateway como um **serviço FastAPI próprio** em `services/gateway`:

- proxy reverso para `/api/auth/*` e `/api/me` na Sprint 1 e para pagamento, captura e armazenamento na Sprint 2;
- validação da assinatura e da expiração do JWT antes de repassar a chamada;
- rate limit no login, no cadastro e no reenvio do código;
- propagação de `X-User-Id`, `X-Request-ID` e do IP de origem;
- `/health/ready` agregado, consumido por `apps/web/src/app/api/health/route.ts`.

TLS e a porta pública ficam num proxy de borda (Caddy, #17), não no gateway.

## Consequências (positivas / negativas)

- (+) Mesma linguagem, lib comum, logs e testes dos outros serviços.
- (+) Regras de autenticação ficam em código Python testável, não em configuração.
- (−) É código a manter: cada rota nova exige mudança no gateway.
- (−) Desempenho de proxy inferior a soluções dedicadas (Nginx, Envoy). Aceitável para o volume esperado, mas deve ser medido no teste de carga (#38).
- (−) Sem o auth com os endpoints (#7–#10), a web ainda depende do mock para desenvolvimento.

## Alternativas consideradas

- **Kong / KrakenD / Traefik com plugins:** prontos e rápidos, mas exigem aprender outra ferramenta e configurar a validação de JWT e o rate limit fora do código do time.
- **Nginx com `auth_request`:** leve, mas espalha a lógica de autenticação entre a configuração do Nginx e um serviço auxiliar.
- **Sem gateway (web chamando cada serviço):** contraria a seção 4.1 e duplica a validação do JWT em todos os serviços.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| Beatriz Marques dos Santos | | |
| Danielle Santos de Souza | | |
| Giovanna Ferrúcio Farani | | |
| Luiz Antony Duarte Ribeiro | | |
