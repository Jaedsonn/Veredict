# ADR-006 – Aplicação Web

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões)

## Contexto

É necessária uma base de fácil acesso e de fácil desenvolvimento para o sistema, considerando as habilidades da equipe (estudantes) e a portabilidade necessária para a aplicação.

## Decisão

Construir o sistema com base na WEB, usufruindo das APIs e conexões.

## Consequências (positivas / negativas)

- (+) Como aplicação WEB, o sistema é facilmente acessado de qualquer dispositivo que tenha um navegador e uma conexão com a internet, sendo assim, a acessibilidade é garantida.
- (−) A compatibilidade com as plataformas (Desktop, Android e iOS) pode ser limitada por diferenças entre os navegadores.

## Implementação

- Next.js 16 com padrão BFF em `apps/web`: [ADR-017](0017-aplicacao-web-nextjs-com-bff.md).
