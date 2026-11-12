# ADR-010 – Divisão dos bancos de dados

- Status: Aceita
- Data: Trabalho II (o documento não registra data)
- Origem: "Estruturação do Veridit", seção 5 (Táticas e decisões); camada de dados na seção 4.1

## Contexto

Pensando em um sistema que envolve provas jurídicas, é necessário que elas estejam armazenadas de forma segura, garantindo assim a recuperabilidade. O sistema precisa apresentar suporte a consultas complexas e relacionamentos bem definidos entre entidades (usuários, pedidos e pagamentos). A equipe precisa de uma solução madura, com boa performance e suporte nativo a dados estruturados e semiestruturados.

## Decisão

Para que isso fosse alcançado, a decisão tomada foi dividir os bancos de dados entre estruturado e não estruturado. O estruturado para armazenar os dados de identificação, pagamento e relatórios; já o não estruturado para armazenamento dos vídeos e fotos. Também foi pensado no uso de object storage, para gerenciar os dados com unidades independentes, o que se torna ideal para dados não estruturados, com acesso via API.

A seção 4.1 detalha três armazenamentos na camada de dados:

1. **Armazenamento de logs:** todos os registros das atividades do sistema, de forma imutável, acessado somente pelo serviço de monitoramento.
2. **Banco de dados central:** usuários, registro de conteúdos, pacotes/créditos e outros; acessado por autenticação, pagamento, captura e armazenamento.
3. **Object Storage:** capturas e gravações de forma imutável, acessado somente pelo serviço de armazenamento.

## Consequências (positivas / negativas)

- (+) A divisão do banco de dados vai evitar que um travamento em uma parte do banco do sistema que não tenha relação com as provas falhe e comprometa as gravações.
- (−) As relações entre os bancos serão feitas de maneira complicada, sendo necessárias mais conexões para ligar uma prova a um advogado ou a um cliente.
- (+) A garantia da recuperabilidade e da segurança dos dados possui uma importância maior.

## Implementação

- SGBD do Banco Central: [ADR-014](0014-mysql-como-banco-de-dados-central.md).
- Armazenamento de logs: [ADR-015](0015-log-storage-em-database-mysql-separada.md).
- Object Storage: [ADR-019](0019-minio-como-object-storage.md).
- Posse das tabelas por serviço: [ADR-020](0020-banco-central-compartilhado-com-posse-por-servico.md).
