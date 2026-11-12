# ADR-019 – MinIO (compatível com S3, com Object Lock) como Object Storage

- Status: Proposta
- Data: 2026-11-12
- Afeta: ADR-004 (recuperabilidade), ADR-010 (divisão dos bancos de dados)

## Contexto

A ADR-010 decide guardar vídeos e fotos num *object storage* "com acesso via API", e a seção 4.1 exige que as capturas fiquem armazenadas "de forma imutável", acessadas só pelo serviço de armazenamento. O documento não define o produto nem como a imutabilidade é garantida.

## Desvio em relação ao documento original

- **Previsto:** um Object Storage imutável, acessado só pelo armazenamento (seção 4.1; ADR-010).
- **No repositório:** ainda não implementado (Sprint 2, #26). O plano dos buckets já está em `docs/banco-de-dados.md`, seção 8.
- **Motivação:** imutabilidade garantida pelo próprio armazenamento, API padrão S3 e execução local em Docker, sem conta em nuvem.

## Decisão

Usar **MinIO** como Object Storage:

- bucket `evidences` com **Object Lock em modo COMPLIANCE** e retenção `EVIDENCE_RETENTION_DAYS` (padrão: 5 anos). Nem o administrador consegue apagar ou sobrescrever um objeto antes do prazo;
- acesso pela API S3, com credenciais exclusivas do serviço de armazenamento;
- o MySQL guarda só os metadados (`object_key`, `version_id`, `sha256`, `size_bytes`). Blob no MySQL é proibido;
- backup diário para fora da máquina (#37).

## Consequências (positivas / negativas)

- (+) Imutabilidade das provas imposta pelo storage, não só pela aplicação (ADR-004).
- (+) API S3: trocar por AWS S3 ou outro provedor compatível no futuro exige pouca mudança.
- (+) Roda localmente e no mesmo `docker compose` do restante.
- (−) Self-hosted: disco, disponibilidade e backup ficam a cargo da equipe.
- (−) COMPLIANCE impede apagar uma prova antes do prazo, inclusive a pedido do titular. Isso é coerente com a regra "provas nunca são apagadas" de `docs/banco-de-dados.md` (seção 9), mas o prazo de retenção precisa ser validado com a equipe à luz da LGPD.
- (−) Object Lock precisa ser habilitado na criação do bucket; não dá para ativar depois.

## Alternativas consideradas

- **AWS S3 (ou GCS) com Object Lock:** gerenciado e mais durável, mas exige conta e custo, e não roda offline no desenvolvimento.
- **Sistema de arquivos local:** sem imutabilidade garantida nem API.
- **Blob no MySQL:** contraria a ADR-010 e incha o banco e os backups.

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| Beatriz Marques dos Santos | | |
| Danielle Santos de Souza | | |
| Giovanna Ferrúcio Farani | | |
| Luiz Antony Duarte Ribeiro | | |
