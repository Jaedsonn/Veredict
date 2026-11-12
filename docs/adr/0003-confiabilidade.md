# ADR-003 – Confiabilidade

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 2.2 (Confiabilidade). No documento a ADR não tem número; ver o [índice](README.md#numeração).

## Contexto

O Veridit parte do princípio de gravação e captura das telas de determinadas aplicações web, como redes sociais. Tendo isso em vista, é importante que esse serviço esteja sempre disponível. Considerando que muitas redes sociais apresentam limite de tempo em suas postagens, não é viável que o Veridit apresente falhas que atrapalhem a captura das informações desejadas e comprometam o usuário.

## Decisão

Nessa situação, a confiabilidade torna-se crítica para garantir a experiência do usuário e a devida utilização do sistema. Por isso, o enfoque nessa característica e sua importância levaram à decisão de que a arquitetura baseada em serviços seria a melhor a ser utilizada. Como as demandas do sistema estão divididas em serviços, isso garante que uma falha em um componente não afetará todo o sistema.

## Consequências (positivas / negativas)

- (+) Garante a experiência do usuário.
- (−) Fortalecer a confiabilidade pode causar alguns gastos com servidor, pela necessidade de manter essa aplicação sempre ativa.
- (−) Haverá a necessidade de manutenção constante para a detecção e correção de falhas, evitando travamentos e similares.

## Implementação

- Estilo arquitetural: [ADR-005](0005-arquitetura-baseada-em-servicos.md).
- Na Sprint 1: timeout de 8 s em toda chamada da web ao gateway (`apps/web/src/lib/config.ts`) e rotas `/health/live` e `/health/ready` em todo serviço (`libs/python/common/src/veriditi_common/health.py`).
- Filas, retentativas e outbox: Sprint 2 (#37), ver [ADR-016](0016-comunicacao-interna-http-fire-and-forget.md).
