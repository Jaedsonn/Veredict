# ADR-001 – Auditabilidade: registros de auditoria isolados e imutáveis

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 2.3 (Auditabilidade)

## Contexto

O Veridit é uma plataforma destinada à coleta, autenticação e preservação de provas digitais com valor probatório judicial. Em processos legais, qualquer indício de adulteração, manipulação de histórico ou perda de rastreabilidade pode invalidar laudos técnicos e levar à recusa da prova em juízo.

## Decisão

Por conta disso, foi decidido isolar os registros de auditoria dos logs comuns da aplicação. Toda ação importante no sistema (como login, criação de prova, cálculo de hash e download de arquivos) será salva de forma automática com o identificador de quem fez, data e hora certas, endereço IP e sem permitir que ninguém edite ou apague esses registros.

## Consequências (positivas / negativas)

- (+) Garante a validade jurídica das provas e a segurança de que o histórico não foi alterado, facilitando perícias e auditorias.
- (−) O sistema terá um consumo maior de espaço em disco ao longo do tempo por guardar tantos detalhes.
- (−) Exige um cuidado a mais no código para registrar cada ação sem deixar o site lento para o usuário.

## Implementação

- Armazenamento e imutabilidade: [ADR-015](0015-log-storage-em-database-mysql-separada.md) e [ADR-020](0020-banco-central-compartilhado-com-posse-por-servico.md).
- Transporte dos eventos: [ADR-016](0016-comunicacao-interna-http-fire-and-forget.md).
- Data e hora precisas: [ADR-021](0021-datas-utc-datetime6.md).
- A web já repassa `X-Forwarded-For` e `User-Agent` ao gateway (`apps/web/src/lib/gateway.ts`), para que o evento registre o IP real.
