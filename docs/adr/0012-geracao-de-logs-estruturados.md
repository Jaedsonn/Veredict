# ADR-012 – Geração de logs estruturados

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões); serviço de monitoramento na seção 4.2.6

## Contexto

Considerando a natureza do sistema, é ideal que cada ação feita seja registrada, a fim de conseguir identificar e traçar o caminho dos objetos armazenados, para fins de auditabilidade e recuperabilidade.

## Decisão

Será registrada toda ação do sistema, considerando o responsável, o que foi feito, quando e como, através de um log estruturado armazenado em paralelo a outras informações do sistema.

O serviço de monitoramento (seção 4.2.6) recebe eventos dos outros serviços no módulo **Logs** e tem um módulo de **Limpeza** que remove logs desnecessários; cada atuação da limpeza também gera uma entrada nos logs.

## Consequências (positivas / negativas)

- (+) Permite associar a responsabilidade de cada ação feita no sistema, garantindo que, caso ocorra um problema, é possível traçar a linha do tempo necessária para isso.

## Implementação

- Logging estruturado e `X-Request-ID` em todos os serviços: #4.
- Ingestão da trilha de auditoria: #5; limpeza de logs operacionais: #35 (Sprint 2).
- Transporte dos eventos: [ADR-016](0016-comunicacao-interna-http-fire-and-forget.md).
