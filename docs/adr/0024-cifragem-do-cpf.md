# ADR-024 – Cifragem do CPF com AES-GCM e índice HMAC

- Status: Proposta
- Data: 2026-11-18
- Afeta: ADR-002 (segurança), ADR-022 (convenções do modelo físico)

## Contexto

O cadastro passa a exigir o CPF de todo usuário (RF22, #60). O CPF é dado pessoal (LGPD) e identifica a pessoa fora da plataforma, então um vazamento do banco não pode expô-lo. Ao mesmo tempo, o sistema precisa:

- garantir que um CPF só tenha uma conta (UNIQUE no banco, sem SELECT antes do INSERT);
- mostrar ao próprio usuário o CPF mascarado (`***.456.789-**`) no perfil.

Hash puro não serve: há só cerca de 10⁹ CPFs válidos, e um SHA-256 sem segredo é revertido por força bruta em minutos. Cifrar sem índice também não serve: o AES-GCM usa nonce aleatório, então o mesmo CPF gera cifras diferentes e o UNIQUE não pega a duplicidade.

## Decisão

Duas colunas e duas chaves independentes:

- **`cpf_enc VARBINARY(64)`**: AES-256-GCM do CPF normalizado (11 dígitos ASCII), com a chave `CPF_ENCRYPTION_KEY`.
  - Formato: `versão (1 byte) || nonce (12 bytes) || cifra (11 bytes) || tag (16 bytes)`, 40 bytes ao todo. O `VARBINARY(64)` deixa folga para uma versão futura.
  - A versão `0x01` identifica algoritmo e chave; uma chave nova entra como versão `0x02`, sem migrar as linhas antigas de uma vez.
  - Nonce de 96 bits de `os.urandom` a cada cifragem. Com o volume esperado, a chance de repetir nonce sob a mesma chave é desprezível.
  - AAD fixo (`veriditi:users.cpf_enc:v1`): amarra a cifra a esta coluna e versão.
    - O AAD fixo permite copiar o `cpf_enc` de uma linha para outra: a cifra copiada continua decifrando. Isso exige DML no banco. A mitigação é o `/me` recalcular o HMAC do CPF decifrado e compará-lo, com `hmac.compare_digest`, ao `cpf_hmac` da linha. Se divergirem, o `/me` falha com o mesmo erro de decifração e registra `cpf_integrity_mismatch` com o `user_id`, sem o CPF.
    - Pôr o `user_id` no AAD foi descartado porque o `id` só existe depois do INSERT. Seria preciso cifrar numa segunda escrita, deixando a linha sem CPF dentro da transação.
- **`cpf_hmac CHAR(64)`** com `uq_users_cpf_hmac`: HMAC-SHA256 dos 11 dígitos com a chave `CPF_HMAC_KEY`, em hex minúsculo (`HashHex`). É determinístico, então o UNIQUE detecta o CPF repetido, e sem a chave não dá para montar o dicionário de CPFs.
- **Chaves**: base64 de 32 bytes cada, obrigatoriamente diferentes (uma chave vazada não compromete a outra função). Ficam no `.env` (dev) e chegam só ao container `auth`; o `auth-migrate` não as recebe.
  - `make keys` gera as duas só quando estão vazias e **nunca** as troca, nem com `force=1`.
  - O auth faz *fail-fast* na subida: chave ausente, base64 inválido, tamanho diferente de 32 bytes ou chaves iguais impedem o `create_app`.
- **Uso**: só o `auth` decifra, e só no `/me`, que devolve o CPF mascarado. O CPF em claro nunca vai para resposta, log, auditoria, exceção ou mensagem de erro. A chave `cpf` (e `cpf_*`) cai no `redact_sensitive` da lib comum.

## Consequências (positivas / negativas)

- (+) Um dump do banco não revela CPFs nem permite confirmar se um CPF está cadastrado sem as chaves.
- (+) A duplicidade continua sendo garantida pelo banco (UNIQUE), sem corrida entre SELECT e INSERT.
- (+) O byte de versão permite trocar a chave de cifra aos poucos.
- (−) **Perder a `CPF_ENCRYPTION_KEY` perde todos os CPFs**: o HMAC ainda garante a unicidade, mas o valor não volta. Backup e custódia das chaves ficam para o #62.
- (−) **Trocar a `CPF_HMAC_KEY` exige decifrar e reindexar todas as linhas** numa migração de dados; não há rotação gradual do índice.
- (−) Quem tem as duas chaves e acesso ao banco lê todos os CPFs: as chaves precisam do mesmo cuidado que a `JWT_PRIVATE_KEY`.
- (−) O 409 `cpf_already_registered` revela que um CPF tem conta (enumeração). Mitigam o rate limit do cadastro e a auditoria; a resposta uniforme fica para o #61.

## Alternativas consideradas

- **Só SHA-256 do CPF**: reversível por força bruta (espaço de 10⁹). Rejeitada.
- **Cifra determinística (AES-SIV) numa coluna só**: daria UNIQUE e decifragem com uma chave, mas mistura as duas funções na mesma chave e revela igualdade entre linhas pela própria cifra. Rejeitada em favor de chaves separadas.
- **Cifragem no MySQL (`AES_ENCRYPT`, TDE)**: a chave passaria pelas queries ou ficaria com o banco, que é justamente o que se quer proteger. Rejeitada.
- **Não guardar o CPF, só o HMAC**: resolveria a unicidade, mas o perfil não conseguiria mostrar o CPF mascarado. Rejeitada pelo critério do #60.

## Implementação

- #60: `services/auth/src/auth_service/adapters/cpf_protector.py` (`AesGcmCpfProtector`, porta `CpfProtector` em `ports.py`), conferência com o `cpf_hmac` em `use_cases/profile.py`, validação das chaves em `config.py`, colunas na migration `0006` (`docs/banco-de-dados.md` §5.1), geração das chaves em `scripts/jwt_keys.py`.
- Pendente: backup e rotação das chaves (#62).

## Aceite da equipe arquiteta

| Integrante | Data | Evidência |
|---|---|---|
| | | |
