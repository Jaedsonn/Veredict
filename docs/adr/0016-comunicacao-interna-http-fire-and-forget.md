# ADR-016 – Comunicação interna por HTTP assíncrono "fire-and-forget" na Sprint 1

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-005 (arquitetura baseada em serviços), ADR-012 (logs estruturados)

## Contexto

No documento, os serviços se comunicam com Notificação por *triggers* (seção 4.2.3) e com Monitoramento por *eventos* (seção 4.2.6). Os dois são internos e nunca recebem chamadas do usuário (seção 4.1). O documento não define o mecanismo de entrega e reconhece, na ADR-005, que "as transmissões não serão automáticas".

Uma fila com entrega garantida (broker, outbox, consumidores, DLQ) é a solução robusta, mas é muita infraestrutura para a Sprint 1, cujo objetivo é a fundação: auth, gateway, notificação e monitoramento.

## Desvio em relação ao documento original

- **Previsto:** *triggers* e *eventos* enviados aos serviços internos, sem mecanismo definido (seções 4.1, 4.2.3 e 4.2.6).
- **No repositório:** interfaces e implementação HTTP em `veriditi_common` (#4): `AuditLogger`/`HttpAuditLogger` em `audit.py` e `Notifier`/`HttpNotifier` em `notifications.py`. Os consumidores ficam no #5 (monitoring) e no #6 (notification).
- **Motivação:** reduzir o escopo da Sprint 1 sem acoplar as regras de negócio ao mecanismo de transporte.

## Decisão

**Sprint 1:**

- Os casos de uso dependem das interfaces `AuditLogger` e `Notifier` (#4), nunca do transporte.
- A implementação da Sprint 1 (`HttpAuditLogger` e equivalente para notificações) agenda a chamada com `BackgroundTasks` do FastAPI e faz `POST /internal/events` (monitoring) ou `POST /internal/notifications` (notification), com um token interno compartilhado.
- A resposta ao usuário não espera a entrega ("fire-and-forget").
- Se a chamada falhar, o evento é escrito no log do próprio serviço com `audit_fallback=true`.
- Se a notificação falhar, o log registra `notification_fallback=true` sem o conteúdo: só `template`, `idempotency_key` e o e-mail mascarado, nunca `data` (que leva o código) nem o destinatário em claro.

**Sprint 2 (#37):** trocar a implementação por outbox transacional + Redis Streams, com retentativas e DLQ. Esta ADR passa então a **Substituída** pela ADR do broker.

## Consequências (positivas / negativas)

- (+) Nenhum broker para operar na Sprint 1.
- (+) A troca para outbox na Sprint 2 muda só a implementação injetada (DIP); nenhuma regra de negócio é alterada.
- (+) Uma falha no Monitoramento ou na Notificação não derruba nem atrasa o login ou o cadastro (ADR-003).
- (−) **Risco aceito:** um evento de auditoria pode se perder se o Monitoramento estiver fora do ar ou se o processo cair antes do envio. Isso enfraquece temporariamente a ADR-001. A mitigação é o outbox na Sprint 2 (#37). Até lá, os eventos perdidos ficam rastreáveis pelo `audit_fallback=true`.
- (−) O mesmo vale para e-mails: um código de verificação pode não ser enviado, e, sem o conteúdo no log, não dá para reenviá-lo a partir dele. A web já oferece o reenvio (#13).

## Alternativas consideradas

- **Chamada HTTP síncrona:** a falha do Monitoramento derrubaria o login, contrariando a ADR-003.
- **Fila já na Sprint 1 (Redis Streams ou RabbitMQ):** resolve a perda, mas antecipa a infraestrutura do #37 e atrasa a fundação.
- **Escrita direta do serviço na `veriditi_logs`:** quebra a posse do Log Storage pelo Monitoramento (seção 4.1; [ADR-015](0015-log-storage-em-database-mysql-separada.md)).

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| Beatriz Marques dos Santos | | |
| Danielle Santos de Souza | | |
| Giovanna Ferrúcio Farani | | |
| Luiz Antony Duarte Ribeiro | | |
